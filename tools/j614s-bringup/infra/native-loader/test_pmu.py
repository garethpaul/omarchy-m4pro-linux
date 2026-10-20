#!/usr/bin/env python3
"""Exercise the actual loader PMU admission function with mocked hardware APIs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def extract(text, name):
    match = re.search(r'static int ' + name + r'\(void\)\s*\{', text)
    if not match:
        raise ValueError('Missing actual PMU function')
    end, depth = match.end(), 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[match.start():end]


PREFIX = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
#define BIT(x) (1U << (x))
static void *adt;
typedef struct spmi_dev { int dummy; } spmi_dev_t;
static spmi_dev_t device;
static int scenario, reads, writes, inits, shutdowns, arms;
static u8 health;
static int adt_path_offset_trace(void *tree, const char *path, int *trace) {
    (void)tree; assert(!strcmp(path, "/arm-io/nub-spmi0")); trace[0]=10;
    return scenario == 0 ? -1 : 10;
}
static int adt_getprop_copy(void *tree, int node, const char *name, void *out, size_t len) {
    (void)tree;
    if (!strcmp(name,"gen")) { assert(node==10 && len==4); *(u32 *)out=scenario==2 ? 2 : 3; return scenario==1 ? -1 : 0; }
    if (!strcmp(name,"is-primary")) { assert(node>=20 && len==4); *(u32 *)out=scenario==5 ? 0 : 1; return scenario==6 ? -1 : 0; }
    if (!strcmp(name,"info-leg_scrpad")) { assert(node>=20 && len==4); *(u32 *)out=scenario==8 ? 0 : 0xf800; return scenario==9 ? -1 : 0; }
    assert(!strcmp(name,"reg") && node>=20 && len==24);
    const u32 reg[6]={14,3,0,4,0,0}; memcpy(out,reg,24);
    if (scenario==10) ((u32 *)out)[5]=1;
    return scenario==11 ? -1 : 0;
}
static int adt_get_reg(void *tree, int *path, const char *name, int index, u64 *base, u64 *size) {
    (void)tree; assert(path[0]==10 && !strcmp(name,"reg") && index==0);
    *base=scenario==3 ? 0x509014004UL : 0x509014000UL;
    *size=scenario==4 ? 0x4004 : 0x4000;
    return scenario==22 ? -1 : 0;
}
static int adt_get_child_count(void *tree, int node) { (void)tree; assert(node==10); return scenario==14 ? 2 : 1; }
static int adt_first_child_offset(void *tree, int node) { (void)tree; assert(node==10); return 20; }
static int adt_next_sibling_offset(void *tree, int node) { (void)tree; return node+1; }
static bool adt_is_compatible(void *tree, int node, const char *compat) { (void)tree; assert(node>=20 && !strcmp(compat,"pmu,spmi")); return scenario!=7; }
static u32 read32(u64 address) {
    assert(address==0x509014000UL || address==0x509014080UL);
    if (address==0x509014000UL) return scenario==12 || (scenario==18 && reads) ? 0 : 0x1000100;
    return scenario==13 || (scenario==26 && reads) ? BIT(27) : 0;
}
static spmi_dev_t *spmi_init(const char *path) { assert(!strcmp(path,"/arm-io/nub-spmi0")); inits++; return scenario==15 ? NULL : &device; }
static int spmi_ext_read_long(spmi_dev_t *dev, u8 address, u16_t_PLACEHOLDER reg, u8 *out, size_t len) {
    assert(dev==&device && address==14 && reg==0xf802 && len==1); reads++; *out=scenario==25 && reads==2 ? 1 : health;
    return scenario==16 || (scenario==17 && reads==2) ? -7 : scenario==23 ? 5 : 0;
}
static int __attribute__((unused)) spmi_ext_write_long(spmi_dev_t *dev, u8 address, u16_t_PLACEHOLDER reg, const u8 *value, size_t len) {
    assert(dev==&device && address==14 && reg==0xf802 && len==1); writes++; health=*value; return 0;
}
static void spmi_shutdown(spmi_dev_t *dev) { assert(dev==&device); shutdowns++; }
'''.replace('u16_t_PLACEHOLDER', 'uint16_t')
PREFIX += r'''
static int __attribute__((unused)) wdt_arm_seconds(unsigned seconds) { assert(seconds==60); arms++; return scenario==24 ? -1 : 0; }
'''
SUFFIX = r'''
int main(int argc, char **argv) {
    assert(argc==2); scenario=atoi(argv[1]); assert(scenario>=0 && scenario<27);
    health=scenario==19 ? 1 : scenario==20 ? 255 : 0;
    int result=invoke();
    bool accepted=(result==0), expected=(scenario==21);
    printf("{\"case\":%d,\"return\":%d,\"writes\":%d,\"reads\":%d,\"inits\":%d,\"shutdowns\":%d,\"arms\":%d}\n",scenario,result,writes,reads,inits,shutdowns,arms);
    if (writes || accepted!=expected || arms!=EXPECTED_ARMS) return 1;
    if (inits && scenario!=15 && shutdowns!=1) return 2;
    return 0;
}
'''
CASES = ['missing_spmi_path','missing_generation','wrong_generation','wrong_mmio_base',
         'wrong_mmio_size','no_primary','missing_primary_property','wrong_pmu_compatible',
         'wrong_scratch_identity','missing_scratch_property','wrong_reg_identity','missing_reg',
         'wrong_controller_identity','controller_busy','duplicate_primary','spmi_init_failure',
         'first_read_error','second_read_error','controller_identity_changes_after_read',
         'health_nonzero_1','health_nonzero_255','health_already_zero','reg_lookup_error','positive_read_error']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--legacy-red-control', action='store_true')
    p.add_argument('--handoff-window', action='store_true', help='Exercise actual guard/watchdog call window too')
    a = p.parse_args()
    text = (a.source/'src/j614s_native.c').read_text()
    name = 'require_zero_health_counter' if 'static int require_zero_health_counter' in text else 'clear_health_counter'
    body = extract(text, name)
    header = (a.source/'src/adt.h').read_text()
    macros = []
    for macro in ('ADT_GETPROP', 'ADT_GETPROP_ARRAY', 'ADT_FOREACH_CHILD'):
        lines = header[header.index('#define '+macro+'('):].splitlines(True)
        count = 1
        while lines[count-1].rstrip().endswith('\\'):
            count += 1
        macros.append(''.join(lines[:count]))
    window = ''
    if a.handoff_window:
        start = text.index('    /* All malloc/SPMI work precedes')
        window = text[start:text.index('    u64 old_heap', start)]
        window = re.sub(r'    j614s_native_note\([^;]+;\n', '', window)
        invoke = 'static int invoke(void) {\n'+window+'\nreturn 0;\n}\n'
    else:
        invoke = 'static int invoke(void) { return '+name+'(); }\n'
    suffix = SUFFIX.replace('EXPECTED_ARMS', '(scenario==21 || scenario==24 ? 1 : 0)' if a.handoff_window else '0')
    code = PREFIX+'\n'+''.join(macros)+'\n'+body+'\n'+invoke+suffix
    results = []
    with tempfile.TemporaryDirectory(prefix='pmu-host-') as temp:
        root = Path(temp); src=root/'pmu.c'; src.write_text(code)
        for compiler in ('gcc', 'clang'):
            binary = root/compiler
            flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all']
            subprocess.run([compiler,*flags,str(src),'-o',str(binary)],check=True,capture_output=True)
            cases=[]
            for i, label in enumerate(CASES+['watchdog_arm_error','health_changes_on_second_read','controller_busy_after_read']):
                if i==24 and not a.handoff_window:
                    continue
                run = subprocess.run([str(binary),str(i)],capture_output=True,text=True)
                expected=1 if a.legacy_red_control and (i not in (21,24) if a.handoff_window else i in (19,20)) else 0
                if run.returncode!=expected or run.stderr:
                    raise RuntimeError(f'{compiler} {label}: exit{run.returncode}, expected{expected}, stderr={run.stderr}')
                row=json.loads(run.stdout);row.update(name=label,exit_code=run.returncode)
                cases.append(row)
            results.append({'compiler':compiler,'flags':flags,'cases':cases})
    report={'status':'EXPECTED_LEGACY_FAILURE_REPRODUCED' if a.legacy_red_control else 'PASS',
            'hardware':'UNTESTED','function':name,'actual_function_sha256':hashlib.sha256(body.encode()).hexdigest(),
            'actual_adt_macros_sha256':hashlib.sha256(''.join(macros).encode()).hexdigest(),
            'policy':'PMU write helper must never be called; only preexisting zero health accepted',
            'sanitizers':'ASan+UBSan fatal; every run requires empty stderr',
            'scope':'Actual unchanged extracted decision function and actual ADT macros; metadata/MMIO/SPMI hardware boundaries mocked',
            'handoff_window_sha256':hashlib.sha256(window.encode()).hexdigest() if window else None,
            'handoff_window_scope':'Actual source guard/arm statements; debug note excluded; full native_run not executed' if window else None,
            'runs':results}
    a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(report['status']+f': {len(results[0]["cases"])} cases x GCC/Clang; fatal sanitizer diagnostics')


if __name__=='__main__':
    main()
