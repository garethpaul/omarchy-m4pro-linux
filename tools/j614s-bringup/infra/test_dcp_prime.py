#!/usr/bin/env python3
"""Exercise actual DRM PRIME dispatch/import functions and the DCP module gate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def extract(text, name):
    match = re.search(r'(?m)^[a-zA-Z_][^;{}]*\b' + name + r'\([^;{}]*\)\s*\{', text)
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
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
typedef uint64_t u64;
typedef uint64_t dma_addr_t;
typedef uint64_t phys_addr_t;
typedef uint64_t resource_size_t;
struct device { int unused; };
struct dma_buf_ops { int unused; };
struct dma_buf { const struct dma_buf_ops *ops; void *priv, *resv; int refs; };
struct dma_buf_attachment { int unused; };
struct sg_table { int unused; };
struct drm_device;
struct drm_gem_object { struct drm_device *dev; size_t size; struct dma_buf_attachment *import_attach; void *resv; int refs; };
struct drm_driver {
    struct drm_gem_object *(*gem_prime_import)(struct drm_device *, struct dma_buf *);
    struct drm_gem_object *(*gem_prime_import_sg_table)(struct drm_device *, struct dma_buf_attachment *, struct sg_table *);
};
struct drm_device { struct drm_driver *driver; struct device *dev; };
struct drm_gem_dma_object { struct drm_gem_object base; dma_addr_t dma_addr; };
struct resource { u64 start, end; };
struct apple_drm_private { struct drm_device drm; struct resource scanout_pool; bool scanout_pool_attached; u64 scanout_iova_base; };
struct apple_drm_gem_object { struct drm_gem_dma_object dma; struct sg_table *scanout_sgt; dma_addr_t pool_dma_addr; bool pool_fixed_iova; };
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define to_drm_gem_dma_obj(p) container_of(p,struct drm_gem_dma_object,base)
#define IS_MODULE(x) MODULE_TEST
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define ERR_CAST(p) ((void *)(p))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define DMA_BIDIRECTIONAL 0
#define dev_err(...) ((void)0)
#define dev_info(...) ((void)0)
static const struct dma_buf_ops drm_gem_prime_dmabuf_ops, foreign_ops;
static struct dma_buf_attachment attachment;
static struct sg_table table;
static struct drm_gem_object imported;
static int attaches, maps, gets, imports;
#if CANDIDATE
static resource_size_t resource_size(const struct resource *r) { return r->end-r->start+1; }
static phys_addr_t dma_to_phys(struct device *d, dma_addr_t a) { (void)d; return a; }
#endif
static void drm_gem_object_get(struct drm_gem_object *o) { gets++; o->refs++; }
static struct device *drm_dev_dma_dev(struct drm_device *d) { return d->dev; }
static struct dma_buf_attachment *dma_buf_attach(struct dma_buf *b, struct device *d) { (void)b; (void)d; attaches++; return &attachment; }
static void get_dma_buf(struct dma_buf *b) { b->refs++; }
static void dma_buf_put(struct dma_buf *b) { b->refs--; }
static struct sg_table *dma_buf_map_attachment_unlocked(struct dma_buf_attachment *a, int dir) { assert(a==&attachment && dir==0); maps++; return &table; }
static void dma_buf_unmap_attachment_unlocked(struct dma_buf_attachment *a, struct sg_table *s, int dir) { assert(a==&attachment && s==&table && dir==0); }
static void dma_buf_detach(struct dma_buf *b, struct dma_buf_attachment *a) { (void)b; assert(a==&attachment); }
static struct drm_gem_object *import_sgt(struct drm_device *d, struct dma_buf_attachment *a, struct sg_table *s) { (void)d; assert(a==&attachment && s==&table); imports++; return &imported; }
'''
SUFFIX = r'''
static void reset(void) { attaches=maps=gets=imports=0; }
int main(void) {
    struct device hw={0}; struct drm_driver driver={.gem_prime_import_sg_table=import_sgt};
    struct apple_drm_private apple={.drm={.driver=&driver,.dev=&hw},.scanout_pool={0x100000,0x10ffff},.scanout_pool_attached=true,.scanout_iova_base=0x400000};
#if CANDIDATE
    struct apple_drm_gem_object pool_obj={.dma={.base={.dev=&apple.drm,.size=16384},.dma_addr=0x100000}};
#endif
    struct dma_buf foreign={.ops=&foreign_ops,.priv=(void *)1};
    struct drm_gem_object *r;
#if CANDIDATE
    driver.gem_prime_import=apple_drm_gem_prime_import;
#endif
    reset(); r=actual_dispatch(&apple.drm,&foreign);
    if (MODULE_TEST && (r!=ERR_PTR(-EOPNOTSUPP) || attaches || maps || imports)) {
        printf("FAIL: actual module PRIME dispatch reached attach=%d map=%d import=%d\n",attaches,maps,imports);
        return 1;
    }
    if (!MODULE_TEST) assert(r==&imported && attaches==1 && maps==1 && imports==1);
#if CANDIDATE
    /* Marker comes from the actual validated no-map allocation path. */
    assert(apple_drm_gem_map_nomap_pool(&pool_obj.dma)==0);
    assert(pool_obj.pool_fixed_iova && pool_obj.dma.dma_addr==0x400000);
    struct dma_buf own={.ops=&drm_gem_prime_dmabuf_ops,.priv=&pool_obj.dma.base};
    reset(); r=actual_dispatch(&apple.drm,&own);
    assert(r==&pool_obj.dma.base && gets==1 && !attaches && !maps && !imports);
    /* Same device/GEM exporter, but not an owned no-map allocation. */
    pool_obj.pool_fixed_iova=false;
    reset(); r=actual_dispatch(&apple.drm,&own);
    if (MODULE_TEST) assert(r==ERR_PTR(-EOPNOTSUPP) && !gets && !attaches && !maps);
    else assert(r==&pool_obj.dma.base && gets==1 && !attaches && !maps);
    /* Genuine GEM exporter from a different device remains foreign. */
    struct drm_device other={0}; pool_obj.dma.base.dev=&other; pool_obj.pool_fixed_iova=true;
    reset(); r=actual_dispatch(&apple.drm,&own);
    if (MODULE_TEST) assert(r==ERR_PTR(-EOPNOTSUPP) && !attaches && !maps && !imports);
    else assert(r==&imported && attaches==1 && maps==1 && imports==1);
    /* Out-of-pool allocation never obtains the ownership marker. */
    pool_obj.dma.base.dev=&apple.drm; pool_obj.dma.dma_addr=0x200000; pool_obj.pool_fixed_iova=false;
    assert(apple_drm_gem_map_nomap_pool(&pool_obj.dma)==-ERANGE && !pool_obj.pool_fixed_iova);
#endif
    printf("PASS: actual PRIME dispatch/core importer and no-map ownership cases (module=%d)\n",MODULE_TEST);
    return 0;
}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', required=True, type=Path)
    ap.add_argument('--baseline', required=True)
    a = ap.parse_args()
    rel = 'drivers/gpu/drm/apple/apple_drv.c'
    current = (a.source / rel).read_text()
    baseline = subprocess.check_output(['git', 'show', a.baseline + ':' + rel], cwd=a.source).decode()
    core = (a.source / 'drivers/gpu/drm/drm_prime.c').read_text()
    assert re.search(r'\.gem_prime_import\s*=\s*apple_drm_gem_prime_import', current)
    assert not re.search(r'\.gem_prime_import\s*=', baseline)
    dispatch = re.search(r'\tif \(dev->driver->gem_prime_import\)\n\t\tobj = dev->driver->gem_prime_import\(dev, dma_buf\);\n\telse\n\t\tobj = drm_gem_prime_import\(dev, dma_buf\);', core).group()
    dispatch = 'static struct drm_gem_object *actual_dispatch(struct drm_device *dev, struct dma_buf *dma_buf) { struct drm_gem_object *obj;\n' + dispatch + '\nreturn obj; }\n'
    common = '\n'.join(extract(core, name) for name in ('drm_gem_is_prime_exported_dma_buf', 'drm_gem_prime_import_dev', 'drm_gem_prime_import'))
    actual = extract(current, 'apple_drm_gem_map_nomap_pool') + extract(current, 'apple_drm_gem_prime_import')
    results = []
    with tempfile.TemporaryDirectory(prefix='dcp-prime-host-') as tmp:
        path = Path(tmp)
        for compiler in ('gcc', 'clang'):
            for candidate, module in ((0, 1), (1, 1), (1, 0)):
                src = path / 'test.c'; exe = path / 'test'
                src.write_text(f'#define MODULE_TEST {module}\n#define CANDIDATE {candidate}\n' + PREFIX + common + (actual if candidate else '') + dispatch + SUFFIX)
                flags = ['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
                subprocess.run([compiler, *flags, str(src), '-o', str(exe)], check=True)
                r = subprocess.run([str(exe)], capture_output=True, text=True)
                assert not r.stderr.strip(), r.stderr
                if candidate:
                    assert r.returncode == 0, r.stderr + r.stdout
                else:
                    assert r.returncode == 1 and 'attach=1 map=1 import=1' in r.stdout, r.stderr + r.stdout
                results.append({'compiler': compiler, 'candidate': bool(candidate), 'module': bool(module), 'exit_code': r.returncode, 'result': r.stdout.strip()})
    print(json.dumps({'status': 'PASS (red baseline / green candidate)', 'baseline': a.baseline, 'source_file_sha256': hashlib.sha256(current.encode()).hexdigest(), 'drm_prime_source_sha256': hashlib.sha256(core.encode()).hexdigest(), 'variants': results, 'scope': 'Actual DRM PRIME dispatch snippet, ownership helper and complete import functions with host DMA API stubs, plus actual no-map marker function. Not live dma-buf/DT/DART validation.'}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
