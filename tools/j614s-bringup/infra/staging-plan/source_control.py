#!/usr/bin/env python3
"""Host-only controls using the actual6249 find_ram and ADT property macros."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def extract(text, name):
    match=re.search(r'static int '+name+r'\([^;{}]*\)\s*\{',text)
    if not match:raise ValueError('Actual source function missing')
    depth,end=1,match.end()
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[match.start():end]


def macro(text,name):
    lines=text[text.index('#define '+name+'('):].splitlines(True);count=1
    while lines[count-1].rstrip().endswith('\\'):count+=1
    return ''.join(lines[:count])


PREFIX=r'''
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>
typedef uint64_t u64;
typedef uint32_t u32;
typedef uint8_t u8;
#define ALIGN_2M(x) (((x)+0x1fffffUL)&~0x1fffffUL)
#define RAM_SIZE (4UL<<30)
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
struct adt_property { char name[32]; u32 size; u8 value[]; };
static union { u64 align; u8 bytes[512]; } data;
static void *adt=data.bytes;
static struct { u64 phys_base,mem_size; } cur_boot_args;
static int count[2];
static int adt_path_offset(void *tree,const char *path) {
    (void)tree;
    if (!strcmp(path,"/chosen/memory-map"))return 0;
    assert(!strcmp(path,"/chosen/carveout-memory-map"));return 1;
}
static int adt_get_property_count(void *tree,int node) {(void)tree;return count[node];}
static int adt_first_property_offset(void *tree,int node) {(void)tree;return node ? 64+3*52 : 64;}
static int adt_next_property_offset(void *tree,int offset) {(void)tree;return offset+52;}
static void property(int node,int idx,const char *name,u64 lo,u64 size) {
    struct adt_property *p=(void *)(data.bytes+(node?64+3*52:64)+idx*52);
    memset(p,0,52);strcpy(p->name,name);p->size=16;
    u64 range[]={lo,size};memcpy(p->value,range,sizeof(range));
}
'''
SUFFIX=r'''
int main(void) {
    const u64 base=0x800000000UL,G=1UL<<30;
    cur_boot_args.phys_base=base;cur_boot_args.mem_size=16*G;
    count[0]=2;count[1]=1;
    property(1,0,"region-id-24",base,16*G);
    property(0,0,"later",base+6*G,G);property(0,1,"earlier",base+G,4*G);
    u64 start=base;assert(find_ram(&start,base+16*G)==0 && start==base+7*G);
    printf("{\"case\":\"unsorted_fixed_point\",\"start_offset\":%llu}\n",(unsigned long long)(start-base));
    property(0,0,"earlier",base+G,4*G);property(0,1,"later",base+6*G,G);
    start=base;assert(find_ram(&start,base+16*G)==0 && start==base+7*G);
    printf("{\"case\":\"sorted_same_result\",\"start_offset\":%llu}\n",(unsigned long long)(start-base));
    property(0,0,"outer",base+G,4*G);property(0,1,"inner",base+2*G,G);
    start=base;assert(find_ram(&start,base+16*G)==0 && start==base+5*G);
    puts("{\"case\":\"nested\",\"result\":0}");
    property(0,0,"sentinel",~0UL,~0UL);property(0,1,"zero",base,0);
    start=base;assert(find_ram(&start,base+16*G)==0 && start==base);
    puts("{\"case\":\"sentinel_zero_and_exact_carveout_exemption\",\"result\":0}");
    property(0,0,"region-id-24",base,16*G);
    start=base;assert(find_ram(&start,base+16*G)==-1);
    puts("{\"case\":\"memory_map_envelope_is_NOT_exempt\",\"result\":-1}");
    property(0,0,"overflow",~0UL-0x1f,0x100);
    start=base;assert(find_ram(&start,base+16*G)==-1);
    puts("{\"case\":\"overflow\",\"result\":-1}");
    return 0;
}
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    if not __debug__:raise SystemExit('Optimized Python prohibited')
    source=(a.source/'src/j614s_native.c').read_bytes()
    if hashlib.sha256(source).hexdigest()!='fc88b9e9da14593896220f5752c7a84896c2007b56f7bd8ba7d562beae4b4118':raise ValueError('Pinned6249 source differs')
    body=extract(source.decode(),'find_ram');header=(a.source/'src/adt.h').read_text();macros=macro(header,'ADT_PROP')+macro(header,'ADT_FOREACH_PROPERTY');runs=[]
    if hashlib.sha256(macros.encode()).hexdigest()!='b80b864aad792e3c1298636304f14112c4c0790744211a89ca06d2c633a70ca3':raise ValueError('Pinned ADT macros differ')
    with tempfile.TemporaryDirectory(prefix='staging-source-host-') as temp:
        root=Path(temp);src=root/'source.c';src.write_text(PREFIX+'\n'+macros+'\n'+body+'\n'+SUFFIX)
        for cc in ('gcc','clang'):
            binary=root/cc;flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all']
            subprocess.run([cc,*flags,str(src),'-o',str(binary)],check=True,capture_output=True)
            test=subprocess.run([str(binary)],capture_output=True,text=True)
            if test.returncode or test.stderr:raise RuntimeError('Actual source host regression failed')
            runs.append({'compiler':cc,'flags':flags,'cases':[json.loads(line) for line in test.stdout.splitlines()],'stderr_bytes':0})
    a.output.write_text(json.dumps({'status':'PASS','hardware':'UNTESTED','source_function_sha256':hashlib.sha256(body.encode()).hexdigest(),'actual_ADT_macros_sha256':hashlib.sha256(macros.encode()).hexdigest(),'runs':runs,'scope':'Actual6249 4GiB find_ram function with mocked ADT transport; not hardware or proof that future4GiB allocation fits'},indent=2,sort_keys=True)+'\n');print('PASS: actual6249 find_ram 6cases x GCC/Clang fatal sanitizers')


if __name__=='__main__':main()
