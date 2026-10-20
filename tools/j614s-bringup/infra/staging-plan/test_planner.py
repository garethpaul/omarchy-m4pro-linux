#!/usr/bin/env python3
"""Wholly synthetic host controls. Never reads target interfaces or actual capture."""
import copy
import hashlib
import itertools
import json
from pathlib import Path
import struct
import types
import unittest

# Execute these exact source bytes; no timestamp-valid __pycache__ fallback.
SOURCE = Path(__file__).with_name('planner.py').read_bytes()
m = types.ModuleType('staging_planner_tested')
exec(compile(SOURCE, 'planner.py', 'exec'), m.__dict__)


def row(source, name, base, size):
    return dict(source=source, name=name, base=base, size=size,
                raw_hex=struct.pack('<QQ', base, size).hex())


def fixture():
    # Invented addresses/layout; only public loader's fixed display guard is reused.
    phys=(1124735713280 & ~((1<<32)-1))-(20<<30)
    lo=phys+(16<<20);resident=lo+(128<<20)
    session=dict(usb_enumeration='99999', observer_sha256=m.OBSERVER_SHA,
                 resident_binary_sha256=m.RESIDENT_SHA, resident_elf_sha256=m.RESIDENT_ELF_SHA,
                 bootargs_sha256='1'*64, adt_sha256='2'*64)
    return dict(schema=1, kind='readonly-j614s-staging-geometry', synthetic_fixture=True,
                captured_utc='synthetic-never-observed', session=session,
                memory=dict(usable_base=lo, usable_size=16<<30, physical_base=phys,
                            physical_size=24<<30, resident_base=resident,
                            resident_end=resident+0x350000, heap_base=resident+(8<<20)+3,
                            heap_limit=0, bootargs_top=resident+(4<<20),
                            boot_video=dict(base=1124735713280, display=1, stride=12096,
                                            width=3024, height=1964, depth=30)),
                ranges=[row('/chosen/memory-map','resident',resident,0x350000),
                        row('/chosen/memory-map','zero',lo,0),
                        row('/chosen/memory-map','sentinel',m.U64_MAX,m.U64_MAX),
                        row('/chosen/carveout-memory-map','region-id-24',lo,16<<30),
                        row('/chosen/carveout-memory-map','outside',phys,4096)],
                protected_metadata=[dict(name='live-bootargs',base=resident+0x1000,size=1152),
                                    dict(name='live-adt',base=resident+0x2000,size=0x4000)],
                bootargs_bytes=1152, cpu_state=dict(secondary_flags_set=11,
                            secondary_slots_idle=True,resident_wfe_mode=True),
                helper_sources=dict(m.HELPERS), target_memory_written=False,
                code_executed_via_call=False, allocator_called=False, cores_started=False,
                watchdog_action='unchanged',exceptions=0,deployment_authorized=False,
                recovery_verified=False)


def inputs(c):
    raw=json.dumps(c,sort_keys=True).encode()
    pins=dict(c['session'], capture_sha256=hashlib.sha256(raw).hexdigest(),
              synthetic_fixture=c['synthetic_fixture'])
    return raw,pins


class Geometry(unittest.TestCase):
    def test_observation_never_places_even_ready_synthetic(self):
        c=fixture();result=m.observe_geometry(*inputs(c))
        self.assertIsNone(result['placement'])
        self.assertFalse(result['deployment_authorized'])
        self.assertFalse(result['reservation_claimed'])
        self.assertIn('NO_VERIFIED_CONTAINER',result['blocked_gates'])
        self.assertNotIn('HEAP_INSIDE_PROTECTED_SPAN',result['blocked_gates'])
        self.assertEqual(result['range_counts'],dict(sentinel=1,zero=1,
                         exact_envelope_exemption=1,protected=1,outside_usable=1))

    def test_heap_inside_carveout_remains_refusal(self):
        c=fixture();heap=c['memory']['heap_base']
        c['ranges'].append(row('/chosen/carveout-memory-map','vendor',heap-4096,128<<20))
        result=m.observe_geometry(*inputs(c))
        self.assertIn('HEAP_INSIDE_PROTECTED_SPAN',result['blocked_gates'])
        self.assertIn('STRICT_HEAP_ADVANCE_UNSAFE',result['blocked_gates'])
        self.assertIsNone(result['placement'])
        _,protected,_=m._capture(*inputs(c))
        child=m.choose_base(heap,m.CHILD_BYTES,heap+(1<<30),protected)
        self.assertGreater(child,heap)
        with self.assertRaisesRegex(ValueError,'HEAP_ADVANCE_CROSSES'):
            m.require_clear_advance(heap,child+m.CHILD_BYTES,protected)

    def test_unsorted_fixed_point_and_nested_all_permutations(self):
        G=1<<30;intervals=[(6*G,7*G),(G,5*G),(2*G,3*G)]
        for sequence in itertools.permutations(intervals):
            self.assertEqual(m.choose_base(0,4*G,16*G,sequence),7*G)
        # A naive one-pass implementation misses the earlier high interval.
        naive=0
        for lo,hi in intervals[:2]:
            if m.overlaps(naive,naive+4*G,lo,hi):naive=m.aligned(hi)
        self.assertTrue(any(m.overlaps(naive,naive+4*G,lo,hi) for lo,hi in intervals))

    def test_separate_child_layout_math_only(self):
        c=fixture();_,protected,_=m._capture(*inputs(c));mem=c['memory']
        child=m.choose_base(max(mem['heap_base'],mem['bootargs_top'],mem['resident_end']),
                            m.CHILD_BYTES,mem['usable_base']+mem['usable_size'],protected)
        m.require_clear_advance(mem['heap_base'],child+m.CHILD_BYTES,protected)
        self.assertEqual(child % (2<<20),0)
        self.assertLess(child+0x800,child+(32<<20))
        self.assertLess(child+m.BOOTARGS_OFFSET+m.BOOTARGS_BYTES,child+m.CHILD_BYTES)
        self.assertEqual(m.aligned(mem['heap_base'],64)-mem['heap_base'],61)

    def test_final_span_clear_is_not_enough(self):
        child=m.choose_base(0,64<<20,512<<20,[(32<<20,96<<20)])
        self.assertEqual(child,96<<20)
        with self.assertRaisesRegex(ValueError,'HEAP_ADVANCE_CROSSES'):
            m.require_clear_advance(0,child+(64<<20),[(32<<20,96<<20)])

    def test_bad_geometry(self):
        for fn in (lambda:m.end_of(m.U64_MAX,1),lambda:m.aligned(m.U64_MAX),
                   lambda:m.aligned(1,3),lambda:m.choose_base(0,64<<20,32<<20,[]),
                   lambda:m.merge([(3,2)]),lambda:m.end_of(True,1),
                   lambda:m.require_clear_advance(0,128,[(64,32)])):
            with self.subTest(fn=fn),self.assertRaises(ValueError):fn()

    def test_capture_mutations_refuse(self):
        changes=[lambda c:c['session'].update(observer_sha256='0'*64),
          lambda c:c['memory'].update(heap_limit=c['memory']['heap_base']-1),
          lambda c:c['memory'].update(resident_end=c['memory']['resident_end']+1),
          lambda c:c['memory']['boot_video'].update(base=0),
          lambda c:c.update(allocator_called=True),lambda c:c.update(bootargs_bytes=1144),
          lambda c:c['protected_metadata'].pop(),
          lambda c:c['ranges'].append(copy.deepcopy(c['ranges'][0])),
          lambda c:c['ranges'][0].update(raw_hex='00'*16),
          lambda c:c['ranges'][0].update(source='/untrusted/map'),
          lambda c:c['ranges'].append(row('/chosen/carveout-memory-map','overflow',m.U64_MAX-5,8)),
          lambda c:c['ranges'][3].update(name='different-envelope'),
          lambda c:c['cpu_state'].update(secondary_flags_set=0)]
        for index,change in enumerate(changes):
            with self.subTest(index=index),self.assertRaises(ValueError):
                c=fixture();change(c);m.observe_geometry(*inputs(c))

    def test_source_sensitive_envelope_rule(self):
        c=fixture();mem=c['memory']
        c['ranges'].append(row('/chosen/memory-map','region-id-24',mem['usable_base'],mem['usable_size']))
        result=m.observe_geometry(*inputs(c))
        self.assertEqual(result['range_counts']['protected'],2)
        self.assertIn('HEAP_INSIDE_PROTECTED_SPAN',result['blocked_gates'])

    def test_pins_hash_and_json_duplicate_refuse(self):
        raw,pins=inputs(fixture())
        for key in ('capture_sha256','usb_enumeration','bootargs_sha256','adt_sha256'):
            changed=dict(pins);changed[key]='0'*64
            with self.subTest(key=key),self.assertRaises(ValueError):m.observe_geometry(raw,changed)
        duplicate=b'{"schema":1,"schema":1}'
        with self.assertRaisesRegex(ValueError,'DUPLICATE_JSON_KEY'):
            m._bound_json(duplicate,hashlib.sha256(duplicate).hexdigest())

    def test_partial_cpu_is_observation_only(self):
        c=fixture();c['cpu_state']=dict(secondary_flags_set=0,secondary_slots_idle=False,resident_wfe_mode=False)
        result=m.observe_geometry(*inputs(c))
        self.assertIn('SECONDARY_SLOTS_NOT_IDLE',result['blocked_gates'])
        self.assertIn('RESIDENT_WFE_FALSE',result['blocked_gates'])
        self.assertIsNone(result['placement'])


if __name__=='__main__':
    if not __debug__:raise SystemExit('Optimized Python prohibited')
    unittest.main()
