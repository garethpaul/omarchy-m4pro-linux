"""Offline geometry observation and interval controls; no placement API or target I/O."""
U64_MAX = (1 << 64) - 1
ALIGNMENT = 2 << 20


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def u64(value):
    return type(value) is int and 0 <= value <= U64_MAX


def end_of(base, size):
    require(u64(base) and u64(size) and size > 0 and size <= U64_MAX-base,
            'INVALID_OR_OVERFLOWING_EXTENT')
    return base+size


def aligned(value, alignment=ALIGNMENT):
    require(u64(value) and type(alignment) is int and 0 < alignment <= U64_MAX and alignment & (alignment-1) == 0,
            'INVALID_ALIGNMENT_INPUT')
    require(value <= U64_MAX-(alignment-1), 'ALIGNMENT_OVERFLOW')
    return (value+alignment-1) & ~(alignment-1)


def overlaps(lo, hi, other_lo, other_hi):
    return lo < other_hi and other_lo < hi


def merge(intervals):
    """Validate, sort and merge nested, overlapping and adjacent ranges."""
    checked=[]
    for lo, hi in intervals:
        require(u64(lo) and u64(hi) and lo < hi, 'INVALID_PROTECTED_INTERVAL')
        checked.append((lo,hi))
    result=[]
    for lo,hi in sorted(checked):
        if result and lo <= result[-1][1]:
            result[-1]=(result[-1][0],max(result[-1][1],hi))
        else:
            result.append((lo,hi))
    return result


def choose_base(floor, span, upper, protected):
    """Internal search only; does NOT authorize heap advancement across gaps."""
    require(u64(upper) and u64(span) and span > 0, 'INVALID_SEARCH_BOUND')
    candidate=aligned(floor)
    normalized=merge(protected)
    for lo,hi in normalized:
        require(candidate <= upper and span <= upper-candidate, 'INSUFFICIENT_CONTIGUOUS_RAM')
        if overlaps(candidate,candidate+span,lo,hi):
            candidate=aligned(hi)
    require(candidate <= upper and span <= upper-candidate, 'INSUFFICIENT_CONTIGUOUS_RAM')
    require(all(not overlaps(candidate,candidate+span,lo,hi) for lo,hi in normalized),
            'SEARCH_OVERLAPS_PROTECTED_INTERVAL')
    return candidate


def require_clear_advance(heap_base, reservation_end, protected):
    require(u64(heap_base) and u64(reservation_end) and heap_base < reservation_end,
            'INVALID_PROSPECTIVE_HEAP_ADVANCE')
    require(all(not overlaps(heap_base,reservation_end,lo,hi) for lo,hi in merge(protected)),
            'HEAP_ADVANCE_CROSSES_PROTECTED_SPAN')

# This profile describes the frozen read-only producer and resident bytes. It is
# not a live-state or recovery grant. No observer module is imported/executed.
import hashlib
import json
import re
import struct

OBSERVER_SHA = 'dbeab84b31fb4861238df54da971378bb4e7fb482a9dc1513c13e37f90af30e9'
RESIDENT_SHA = 'fb31c765c54b2c8108ac7598c8307f663b91fb25ef9cbeb88e75bafffc0f3afb'
RESIDENT_ELF_SHA = '4a32c15fbda69acc47175f1e6b514cfb7d5920916df7630dec216c29177fc28f'
HELPERS = {'cpu_observer_sha256':'fce3a31052563734305b5c475bce7d247cf0c716fb0d0f177b81acf1da3c55d7',
           'staging_memory_sha256':'42860b7b024cb14dfcfd0c81dcaa460cba79f0f121f03a750ee14da76f464a8a'}
SOURCES = {'/chosen/memory-map','/chosen/carveout-memory-map'}
BOOTARGS_BYTES = 1152
CHILD_BYTES = 64 << 20
BOOTARGS_OFFSET = 32 << 20


def _pairs(items):
    result={}
    for key,value in items:
        require(key not in result,'DUPLICATE_JSON_KEY');result[key]=value
    return result


def _bound_json(raw, expected_sha):
    require(type(raw) is bytes and len(raw) <= 4 << 20 and type(expected_sha) is str and re.fullmatch('[0-9a-f]{64}',expected_sha), 'INVALID_PINNED_INPUT')
    require(hashlib.sha256(raw).hexdigest() == expected_sha,'INPUT_HASH_CHANGED')
    result=json.loads(raw.decode(),object_pairs_hook=_pairs)
    require(type(result) is dict,'JSON_OBJECT_REQUIRED')
    return result


def _capture(raw, expected):
    c=_bound_json(raw,expected['capture_sha256'])
    require(type(c['schema']) is int and c['schema']==1 and c['kind']=='readonly-j614s-staging-geometry','CAPTURE_SCHEMA_DIFFERS')
    require(type(c['synthetic_fixture']) is bool and c['synthetic_fixture'] is expected['synthetic_fixture'],'SYNTHETIC_LABEL_DIFFERS')
    keys={'usb_enumeration','observer_sha256','resident_binary_sha256','resident_elf_sha256','bootargs_sha256','adt_sha256'}
    require(type(c['session']) is dict and set(c['session']) == keys,'SESSION_SCHEMA_DIFFERS')
    for key in keys:require(c['session'][key] == expected[key],'SESSION_OR_PAIRED_HASH_CHANGED')
    require(type(expected['usb_enumeration']) is str and re.fullmatch('[0-9]+',expected['usb_enumeration']),'USB_SESSION_PIN_INVALID')
    for key in keys-{'usb_enumeration'}:require(type(expected[key]) is str and re.fullmatch('[0-9a-f]{64}',expected[key]),'SESSION_HASH_INVALID')
    require(c['session']['observer_sha256']==OBSERVER_SHA and c['session']['resident_binary_sha256']==RESIDENT_SHA and c['session']['resident_elf_sha256']==RESIDENT_ELF_SHA and c['helper_sources']==HELPERS,'FROZEN_SOURCE_OR_HELPER_DIFFERS')
    for key in ('target_memory_written','code_executed_via_call','allocator_called','cores_started','deployment_authorized','recovery_verified'):
        require(c[key] is False,'CAPTURE_EXCEEDS_READONLY_CONTRACT')
    require(c['watchdog_action']=='unchanged' and type(c['exceptions']) is int and c['exceptions']==0,'CAPTURE_EXCEPTION_OR_WATCHDOG_DIFFERS')
    require(type(c['bootargs_bytes']) is int and c['bootargs_bytes']==BOOTARGS_BYTES,'BOOTARGS_LAYOUT_DIFFERS')
    m=c['memory'];memkeys={'usable_base','usable_size','physical_base','physical_size','resident_base','resident_end','heap_base','heap_limit','bootargs_top','boot_video'}
    require(type(m) is dict and set(m)==memkeys and all(u64(m[k]) for k in memkeys-{'boot_video'}),'MEMORY_SCHEMA_DIFFERS')
    lo=m['usable_base'];hi=end_of(lo,m['usable_size']);physical_end=end_of(m['physical_base'],m['physical_size'])
    require(m['physical_base'] <= lo < hi <= physical_end and m['physical_base']==lo & ~((1<<32)-1) and m['physical_size']==24<<30,'PHYSICAL_USABLE_ENVELOPES_INVALID')
    require(lo<=m['resident_base']<m['resident_end']<=m['bootargs_top']<=m['heap_base']<=hi and m['resident_end']-m['resident_base']==0x350000,'RESIDENT_HEAP_ORDER_INVALID')
    require(m['heap_limit']==0 or m['heap_base']<=m['heap_limit']<=hi,'HEAP_LIMIT_INVALID')
    video=m['boot_video'];require(type(video) is dict and set(video)=={'base','display','stride','width','height','depth'} and all(u64(x) for x in video.values()),'VIDEO_SCHEMA_INVALID')
    require(video['base']==1124735713280 and video['display'] and video['width']==3024 and video['height']==1964 and video['stride']==12096 and video['depth'] & 0xff ==30,'EXACT_6249_VIDEO_GUARD_DIFFERS')
    video_end=end_of(video['base'],video['stride']*video['height'])
    require(video['base'] % 0x4000==0 and m['physical_base']<=video['base']<video_end<=physical_end and not overlaps(lo,hi,video['base'],video_end),'FRAMEBUFFER_NOT_SEPARATELY_OWNED')
    protected=[(m['resident_base'],m['resident_end']),(video['base'],video_end)]
    if m['heap_base']>m['resident_end']:protected.append((m['resident_end'],m['heap_base']))
    metadata=c['protected_metadata'];require(type(metadata) is list and len(metadata)==2 and {r['name'] for r in metadata}=={'live-bootargs','live-adt'},'PROTECTED_METADATA_SCHEMA_DIFFERS')
    for row in metadata:
        require(set(row)=={'name','base','size'},'PROTECTED_METADATA_FIELDS_DIFFER')
        end=end_of(row['base'],row['size']);require(lo<=row['base']<end<=hi,'LIVE_METADATA_OUTSIDE_USABLE_RAM')
        if row['name']=='live-bootargs':require(row['size']==BOOTARGS_BYTES,'LIVE_BOOTARGS_EXTENT_DIFFERS')
        protected.append((row['base'],end))
    rows=c['ranges'];require(type(rows) is list and 0<len(rows)<=8192,'RANGE_LIST_INVALID')
    seen=set();source_counts={s:0 for s in SOURCES};counts={'sentinel':0,'zero':0,'exact_envelope_exemption':0,'protected':0,'outside_usable':0}
    for row in rows:
        require(type(row) is dict and set(row)=={'source','name','raw_hex','base','size'} and row['source'] in SOURCES,'RANGE_SOURCE_OR_SCHEMA_INVALID')
        require(type(row['name']) is str and 0<len(row['name'])<=128 and '\0' not in row['name'],'RANGE_NAME_INVALID')
        identity=(row['source'],row['name']);require(identity not in seen,'DUPLICATE_RANGE_PROPERTY');seen.add(identity);source_counts[row['source']]+=1
        require(type(row['raw_hex']) is str and re.fullmatch('[0-9a-f]{32}',row['raw_hex']) and u64(row['base']) and u64(row['size']),'RAW_RANGE_INVALID')
        base,size=struct.unpack('<QQ',bytes.fromhex(row['raw_hex']));require((base,size)==(row['base'],row['size']),'RAW_RANGE_DECODE_DIFFERS')
        if base==size==U64_MAX:kind='sentinel'
        else:
            require(size <= U64_MAX-base,'RANGE_OVERFLOW')
            if row['source']=='/chosen/carveout-memory-map' and row['name']=='region-id-24':
                require((base,size)==(lo,m['usable_size']),'FULL_ENVELOPE_EXEMPTION_DIFFERS');kind='exact_envelope_exemption'
            elif size==0:kind='zero'
            elif overlaps(lo,hi,base,base+size):protected.append((max(lo,base),min(hi,base+size)));kind='protected'
            else:kind='outside_usable'
        counts[kind]+=1
    require(all(0<n<=4096 for n in source_counts.values()) and counts['exact_envelope_exemption']==1,'EXACT_ADT_SOURCE_SECTIONS_REQUIRED')
    cpu=c['cpu_state'];require(type(cpu) is dict and set(cpu)=={'secondary_flags_set','secondary_slots_idle','resident_wfe_mode'} and type(cpu['secondary_flags_set']) is int and 0<=cpu['secondary_flags_set']<=11 and type(cpu['secondary_slots_idle']) is bool and type(cpu['resident_wfe_mode']) is bool,'CPU_OBSERVATION_SCHEMA_INVALID')
    require(not cpu['secondary_slots_idle'] or cpu['secondary_flags_set']==11,'CPU_SUMMARY_INCONSISTENT')
    return c,merge(protected),counts


def _observation(c, protected, counts, capture_sha):
    cpu=c['cpu_state'];blocked=['LIVE_FRESHNESS_UNQUALIFIED','RESERVATION_NOT_CLAIMED','RECOVERY_UNTESTED']
    if not cpu['secondary_slots_idle'] or cpu['secondary_flags_set']!=11:blocked.append('SECONDARY_SLOTS_NOT_IDLE')
    if not cpu['resident_wfe_mode']:blocked.append('RESIDENT_WFE_FALSE')
    if any(lo <= c['memory']['heap_base'] < hi for lo,hi in protected):
        blocked.extend(['HEAP_INSIDE_PROTECTED_SPAN','STRICT_HEAP_ADVANCE_UNSAFE'])
    return {'schema':1,'status':'GEOMETRY_OBSERVATION_ONLY','hardware':'UNTESTED','synthetic_fixture':c['synthetic_fixture'],'capture_sha256':capture_sha,'session':dict(c['session']),'memory':dict(c['memory']),'range_counts':counts,'protected_intervals':[list(x) for x in protected],'blocked_gates':blocked,'placement':None,'reservation_claimed':False,'deployment_authorized':False,'target_memory_written':False,'source_invariants':'Paired frozen observer/helper, raw16B ranges, resident/liveheap/bootargs/ADT/video protection; no4GiB-fit claim'}


def observe_geometry(capture_bytes, expected_pins):
    """Return PRIVATE observation only. Never picks a child without verified facts."""
    try:
        c,protected,counts=_capture(capture_bytes,expected_pins)
    except (KeyError, TypeError, UnicodeError, struct.error) as error:
        raise ValueError('MALFORMED_CAPTURE_OR_EXPECTED_PINS') from error
    result=_observation(c,protected,counts,expected_pins['capture_sha256'])
    result['blocked_gates'].append('NO_VERIFIED_CONTAINER')
    return result
