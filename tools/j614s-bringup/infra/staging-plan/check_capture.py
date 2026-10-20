#!/usr/bin/env python3
"""Disk-only replay of the frozen capture; prints no addresses or raw ADT data."""
import argparse
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent
SOURCE=HERE.joinpath('planner.py').read_bytes()
m=types.ModuleType('staging_planner_checked')
exec(compile(SOURCE,'planner.py','exec'),m.__dict__)
EXPECTED={
    'capture_sha256':'af303859c7cfd853e85b509a0a14c8fed5eb4ea240eaf73f13bd77c1df80f78d',
    'synthetic_fixture':False,'usb_enumeration':'63','observer_sha256':m.OBSERVER_SHA,
    'resident_binary_sha256':m.RESIDENT_SHA,'resident_elf_sha256':m.RESIDENT_ELF_SHA,
    'bootargs_sha256':'1a2b271f7cc02878edb0b4a919df814539d9567cdba86a196164becbbce3368e',
    'adt_sha256':'ee5d2412e0cee64ad8861bcdc3cb2301e393041b746355c8fd3759062f3cf96a'}


def check(path):
    raw=path.read_bytes();result=m.observe_geometry(raw,EXPECTED)
    required={'SECONDARY_SLOTS_NOT_IDLE','RESIDENT_WFE_FALSE','HEAP_INSIDE_PROTECTED_SPAN',
              'STRICT_HEAP_ADVANCE_UNSAFE','NO_VERIFIED_CONTAINER'}
    m.require(required<=set(result['blocked_gates']),'ACTUAL_BLOCKERS_DIFFER')
    m.require(result['placement'] is None and result['reservation_claimed'] is False and
              result['deployment_authorized'] is False and result['target_memory_written'] is False,
              'OBSERVATION_EXCEEDS_SCOPE')
    c,protected,_=m._capture(raw,EXPECTED);mem=c['memory']
    prospective=m.choose_base(mem['heap_base'],m.CHILD_BYTES,
                    mem['usable_base']+mem['usable_size'],protected)
    # Private scalar remains local; it is NOT emitted or a candidate placement.
    try:m.require_clear_advance(mem['heap_base'],prospective+m.CHILD_BYTES,protected)
    except ValueError as error:m.require(str(error)=='HEAP_ADVANCE_CROSSES_PROTECTED_SPAN','UNEXPECTED_REFUSAL')
    else:raise ValueError('ACTUAL_STRICT_GAP_EXPECTED_TO_REFUSE')
    m.require(path.read_bytes()==raw,'CAPTURE_CHANGED_DURING_REPLAY')
    return {key:result[key] for key in ('schema','status','hardware','synthetic_fixture',
         'capture_sha256','range_counts','blocked_gates','placement','reservation_claimed',
         'deployment_authorized','target_memory_written')} | {
         'planner_sha256':hashlib.sha256(SOURCE).hexdigest(),
         'capture_unchanged':True,'strict_gap_control':'HEAP_ADVANCE_CROSSES_PROTECTED_SPAN',
         'scope':'Disk-only replay; no actual container, reservation, freshness or recovery qualification'}


if __name__=='__main__':
    if not __debug__:raise SystemExit('Optimized Python prohibited')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path)
    args=parser.parse_args()
    print(json.dumps(check(args.capture),indent=2,sort_keys=True))
