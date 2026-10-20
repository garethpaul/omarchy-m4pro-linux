#!/usr/bin/env python3
"""Offline tests: real pinned binary contract, wholly synthetic memory geometry."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest

HERE=Path(__file__).resolve().parent
WORK=HERE.parents[2]
def load(path,name):
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec',dont_inherit=True,optimize=0),module.__dict__)
    return module
r=load(HERE/'reservation.py','reservation_tested')
f=load(HERE.parent/'staging-plan/test_planner.py','synthetic_fixtures')
BINARY={key:path.read_bytes() for key,path in {
 'planner':HERE.parent/'staging-plan/planner.py','source':WORK/'m1n1/src/heapblock.c',
 'flat':WORK/'m1n1/build/m1n1.bin','elf':WORK/'m1n1/build/m1n1-raw.elf',
 'instructions':WORK/'overnight-bringup/recovery/allocator-instructions.json'}.items()}


def inputs():
    c=f.fixture();boot=b'\x5a'*1152;c['session']['bootargs_sha256']=hashlib.sha256(boot).hexdigest()
    raw=c['memory']['heap_base']
    c['ranges'].append(f.row('/chosen/carveout-memory-map','synthetic-vendor',raw-4096,128<<20))
    capture,pins=f.inputs(c)
    kwargs=dict(binary_inputs=BINARY,container_sha256='3'*64,container_length=8192,
        bootargs_bytes=boot,bootargs_sha256=c['session']['bootargs_sha256'],expected_raw_heap=raw)
    return c,capture,pins,kwargs


def function(source,name):
    start=source.index('void *'+name+'(');brace=source.index('{',start);end=brace+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]


class Reservation(unittest.TestCase):
    def test_actual_contract_and_clear_synthetic_child_over_gap(self):
        c,raw,pins,kw=inputs();p=r.plan_private(raw,pins,**kw)
        self.assertGreater(p['child_base'],c['memory']['heap_base']+(64<<20))
        self.assertEqual(p['expected_heap_after'],p['child_base']+(64<<20))
        self.assertEqual(p['expected_allocation_return']%64,0)
        self.assertEqual(p['required_bootargs_delta'],dict(field='top_of_kernel_data',old=c['memory']['bootargs_top'],new=p['expected_heap_after'],other_fields='UNCHANGED'))
        self.assertEqual(p['final_bootargs_payload'],'NOT_CONSTRUCTED_OR_VERIFIED')
        self.assertFalse(p['skipped_ranges_writable']);self.assertFalse(p['deployment_authorized'])
        # Strict default still refuses this exact synthetic gap geometry.
        m=r.verify_binary_contract(BINARY);_,protected,_=m._capture(raw,pins)
        with self.assertRaisesRegex(ValueError,'HEAP_ADVANCE_CROSSES'):
            m.require_clear_advance(p['raw_heap'],p['expected_heap_after'],protected)

    def test_absent_or_tampered_contract(self):
        _,raw,pins,kw=inputs()
        for key in (None,*BINARY):
            with self.subTest(key=key),self.assertRaises(ValueError):
                changed=dict(kw)
                if key is None:changed['binary_inputs']=None
                else:
                    changed['binary_inputs']=dict(BINARY)
                    changed['binary_inputs'][key]=BINARY[key]+b'X'
                r.plan_private(raw,pins,**changed)

    def test_inputs_and_bounds_refuse(self):
        _,raw,pins,kw=inputs()
        mutations=[dict(container_length=32<<20),dict(container_length=2048),
                   dict(container_length=True),dict(bootargs_bytes=b'changed'),
                   dict(expected_raw_heap=kw['expected_raw_heap']+1),dict(container_sha256='unverified')]
        for change in mutations:
            with self.subTest(change=list(change)),self.assertRaises(ValueError):
                r.plan_private(raw,pins,**(kw|change))
        c,_,_,kw=inputs();c['memory']['heap_limit']=c['memory']['heap_base']+(64<<20)
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT'):
            r.plan_private(*f.inputs(c),**kw)

    def test_allocation_overflow_and_limit(self):
        for args in ((0,64,1024,0),(r.U64-30,64,r.U64,0),
                     (64,r.U64,1024,0),(65,64,1024,128),(65,64,128,0),
                     (True,64,1024,0)):
            with self.subTest(args=args),self.assertRaises(ValueError):r.allocation_math(*args)
        self.assertEqual(r.allocation_math(65,128,256,256),(128,256))

    def test_actual_allocator_no_arena_writes_causal_control(self):
        source=BINARY['source'].decode();bodies=function(source,'heapblock_alloc')+'\n'+function(source,'heapblock_alloc_aligned')
        prefix='''#include <stdint.h>\n#include <stddef.h>\n#include <assert.h>\n#include <stdlib.h>\n#include <string.h>\n#define panic(...) abort()\nstatic void *heap_base,*heap_limit;\nvoid *heapblock_alloc_aligned(size_t,size_t);\n'''
        suffix='''
_Alignas(64) static unsigned char arena[32768],saved[32768];
int main(void) {
  for (size_t offset=1;offset<64;offset++) {
    memset(arena,0xa5,sizeof(arena));memcpy(saved,arena,sizeof(arena));
    heap_base=arena+offset;heap_limit=arena+sizeof(arena);
    uintptr_t aligned=((uintptr_t)heap_base+63)&~(uintptr_t)63;
    void *returned=heapblock_alloc(8192);
    if ((uintptr_t)returned!=aligned || (uintptr_t)heap_base!=aligned+8192) return 21;
    if (heap_limit!=arena+sizeof(arena)) return 22;
    if (memcmp(arena,saved,sizeof(arena))) return 23;
  }
  return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='allocator-contract-host-') as tmp:
            for cc in ('gcc','clang'):
                for writing in (False,True):
                    body=bodies.replace('heap_base = (void *)(block + size);',
                        'memset((void *)block, 0, size);\n    heap_base = (void *)(block + size);') if writing else bodies
                    path=Path(tmp)/'host.c';binary=Path(tmp)/'host';path.write_text(prefix+body+suffix)
                    subprocess.run([cc,'-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                        '-fsanitize=address,undefined','-fno-sanitize-recover=all',str(path),'-o',str(binary)],check=True,capture_output=True)
                    result=subprocess.run([str(binary)],capture_output=True)
                    self.assertEqual(result.returncode,23 if writing else 0)
                    self.assertEqual(result.stderr,b'')


if __name__=='__main__':
    if not __debug__:raise SystemExit('Optimized Python prohibited')
    unittest.main()
