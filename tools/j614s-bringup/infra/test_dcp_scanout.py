#!/usr/bin/env python3
"""Compile actual DCP pool/bind functions against host metadata stubs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def extract(text, name):
    match = re.search(r'static [^;{}]*\b' + name + r'\([^;{}]*\)\s*\{', text)
    if not match:
        raise ValueError('Missing actual function: ' + name)
    depth, end = 1, match.end()
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[match.start():end] + '\n'


PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint64_t u64;
typedef uint64_t resource_size_t;
struct resource { u64 start, end; };
struct device_node { int unused; };
struct device { struct device_node *of_node; };
struct apple_drm_private { struct resource scanout_pool; bool scanout_pool_attached; u64 scanout_iova_base; };
#define DART_PAGE_SIZE 16384
#define DMA_BIT_MASK(n) ((UINT64_C(1) << (n)) - 1)
#define IS_ALIGNED(x,a) (!((x) & ((a)-1)))
#define IS_MODULE(x) MODULE_TEST
#define dev_err(...) ((void)0)
#define dev_info(...) ((void)0)
static bool use_nomap, missing_pool, missing_name, available, shared, nomap, missing_iova;
static bool read_iova;
static int binds, attaches, attach_result;
static struct resource pool;
static struct device_node node;
static u64 iova;
static resource_size_t resource_size(const struct resource *r) { return r->end-r->start+1; }
static int of_property_match_string(struct device_node *n, const char *p, const char *v) {
    (void)n; assert(!strcmp(p,"memory-region-names")); assert(!strcmp(v,"scanout-pool")); return missing_name ? -ENOENT : 0;
}
static struct device_node *of_parse_phandle(struct device_node *n, const char *p, int idx) {
    (void)n; assert(!strcmp(p,"memory-region")); assert(idx == 0); return missing_pool ? NULL : &node;
}
static bool of_device_is_available(struct device_node *n) { assert(n == &node); return available; }
static bool of_device_is_compatible(struct device_node *n, const char *p) { assert(n == &node); assert(!strcmp(p,"shared-dma-pool")); return shared; }
static bool of_property_read_bool(struct device_node *n, const char *p) {
    (void)n; if (!strcmp(p,"no-map")) return nomap;
    assert(!strcmp(p,"apple,scanout-memory-is-nomap")); return use_nomap;
}
static int of_address_to_resource(struct device_node *n, int idx, struct resource *r) { assert(n == &node && idx == 0); *r=pool; return 0; }
static void of_node_put(struct device_node *n) { assert(n == &node); }
static int of_property_read_u64(struct device_node *n, const char *p, u64 *v) {
    (void)n; assert(!strcmp(p,"apple,scanout-iova-base")); read_iova=true; *v=iova; return missing_iova ? -ENOENT : 0;
}
static int of_reserved_mem_device_init_by_name(struct device *d, struct device_node *n, const char *v) {
    (void)d; (void)n; assert(!strcmp(v,"scanout-pool")); assert(read_iova); attaches++; return attach_result;
}
static int component_bind_all(struct device *d, struct apple_drm_private *a) {
    (void)d; if (use_nomap) assert(a->scanout_pool_attached && attaches == 1 && read_iova); binds++; return 0;
}
'''
SUFFIX = r'''
static int checks;
static void reset(void) {
    use_nomap=available=shared=nomap=true; missing_pool=missing_name=missing_iova=read_iova=false;
    binds=attaches=attach_result=0; pool=(struct resource){0x100000,0x10ffff}; iova=0x400000;
}
static void test(int expected, int expected_attach, int expected_bind) {
    struct device d={&node}; struct apple_drm_private a={0};
    assert(apple_drm_prepare_and_bind(&d,&a) == expected);
    assert(attaches == expected_attach && binds == expected_bind);
    if (expected_bind && use_nomap) assert(a.scanout_iova_base == iova);
    checks++;
}
int main(void) {
    reset(); use_nomap=false; test(MODULE_TEST ? -EOPNOTSUPP : 0,0,MODULE_TEST ? 0 : 1);
    reset(); missing_name=true; test(-ENOENT,0,0);
    reset(); missing_pool=true; test(-ENODEV,0,0);
    reset(); available=false; test(-ENODEV,0,0);
    reset(); shared=false; test(-ENODEV,0,0);
    reset(); nomap=false; test(-ENODEV,0,0);
    reset(); pool.start++; test(-EINVAL,0,0);
    reset(); pool.end--; test(-EINVAL,0,0);
    reset(); pool.end=pool.start-1; test(-EINVAL,0,0);
    reset(); missing_iova=true; test(-ENOENT,0,0);
    reset(); iova++; test(-EINVAL,0,0);
    reset(); iova=UINT64_C(1)<<42; test(-EINVAL,0,0);
    reset(); iova=(UINT64_C(1)<<42)-DART_PAGE_SIZE; test(-EINVAL,0,0);
    reset(); attach_result=-EIO; test(-EIO,1,0);
    reset(); test(0,1,1);
    reset(); iova=0; test(0,1,1);
    printf("PASS: %d actual-source scanout/bind cases (module=%d)\n",checks,MODULE_TEST);
    return 0;
}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', required=True, type=Path)
    ap.add_argument('--baseline', required=True)
    a = ap.parse_args()
    relative = 'drivers/gpu/drm/apple/apple_drv.c'
    current = (a.source / relative).read_text()
    baseline = subprocess.check_output(['git', 'show', a.baseline + ':' + relative], cwd=a.source).decode()
    actual = '\n'.join(extract(current, n) for n in ('apple_get_scanout_pool_resource', 'apple_drm_setup_scanout_pool', 'apple_drm_prepare_and_bind'))
    init = extract(current, 'apple_drm_init')
    assert 'component_bind_all(' not in init
    assert init.index('apple_drm_prepare_and_bind(') < init.index('drmm_mode_config_init(')
    fallback = ('apple_drm_gem_restore_direct_map', 'apple_drm_gem_remove_direct_map')
    results = []
    with tempfile.TemporaryDirectory(prefix='dcp-pool-host-') as tmp:
        root = Path(tmp)
        for compiler in ('gcc', 'clang'):
            for module in (0, 1):
                src = root / 'test.c'; exe = root / 'test'
                src.write_text('#define MODULE_TEST ' + str(module) + '\n' + PREFIX + actual + SUFFIX)
                subprocess.run([compiler, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(src), '-o', str(exe)], check=True)
                output = subprocess.check_output([str(exe)]).decode().strip()
                results.append({'compiler': compiler, 'module': bool(module), 'result': output})
            expanded = []
            for text in (baseline, current):
                raw = '#define IS_BUILTIN(x) 1\n' + '\n'.join(extract(text, n) for n in fallback)
                expanded.append(subprocess.check_output([compiler, '-E', '-P', '-x', 'c', '-'], input=raw.encode()).decode().split())
            assert expanded[0] == expanded[1], 'Built-in direct-map fallback changed'
            raw = '#define IS_BUILTIN(x) 0\n' + '\n'.join(extract(current, n) for n in fallback)
            module_code = subprocess.check_output([compiler, '-E', '-P', '-x', 'c', '-'], input=raw.encode()).decode()
            for name in ('can_set_direct_map', 'set_direct_map_invalid_noflush', 'set_direct_map_default_noflush', 'dcache_clean_inval_poc'):
                assert name not in module_code, 'Module retains private arch call'
    print(json.dumps({'status': 'PASS', 'source_file_sha256': hashlib.sha256(current.encode()).hexdigest(), 'baseline': a.baseline, 'cases_per_variant': 16, 'variants': results, 'builtin_direct_map_fallback': 'preprocessed actual functions unchanged under GCC and Clang', 'module_private_arch_references': 'absent from preprocessed actual fallback functions', 'scope': 'Host metadata/API stubs exercise actual source control flow; not live DT, DART or display validation'}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
