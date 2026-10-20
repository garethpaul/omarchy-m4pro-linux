"""Offline private geometry under an explicit nonwriting allocator contract. No I/O."""
import hashlib
import json
import struct
import types

PINS={
 'planner':'e8b9d4ce0da16f20ad0f205a3dbe2bfa0a6621b2b37ed86d6e9fca872e223363',
 'source':'8f32744ef80273be9a42cef82b9f53667369adb4f9a1588a3a9124546bfa43e5',
 'flat':'fb31c765c54b2c8108ac7598c8307f663b91fb25ef9cbeb88e75bafffc0f3afb',
 'elf':'4a32c15fbda69acc47175f1e6b514cfb7d5920916df7630dec216c29177fc28f',
 'instructions':'f6108800b09d763c76d19749119c91eea47e3532275ecea1d6e699bc5e55a201'}
FUNCTIONS={
 'heapblock_alloc':(135704,136,'7ca42391becaff263698824eb3b7aadf98d69418f2951312c01afc479d91eb4b'),
 'heapblock_alloc_aligned':(135892,200,'1700153c4f0d218bac159d7c3b8f7b72cf42a71c116c2e0908ce9c3368679977'),
 'heapblock_high_water':(135880,12,'2a1847cc59e14723b70a9a86972d516de7aac0987abb93a5dd210017119913cc')}
U64=(1<<64)-1


def require(ok,reason):
    if not ok:raise ValueError(reason)


def digest(data):
    require(type(data) is bytes,'BYTES_REQUIRED')
    return hashlib.sha256(data).hexdigest()


def verify_binary_contract(inputs):
    """Require original bytes, not a caller-supplied verified boolean or receipt."""
    require(type(inputs) is dict and set(inputs)==set(PINS),'EXPLICIT_BINARY_CONTRACT_REQUIRED')
    for key,value in PINS.items():require(digest(inputs[key])==value,'CONTRACT_BYTES_DIFFER_'+key)
    elf=inputs['elf'];flat=inputs['flat'];evidence=json.loads(inputs['instructions'])
    require(elf[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',elf,18)[0]==183,'ELF_ARCH_DIFFERS')
    # SHA-pinned ELF is trusted structurally; independently bind named symbol extents.
    shoff=struct.unpack_from('<Q',elf,40)[0];entsize,count=struct.unpack_from('<HH',elf,58)
    require(entsize==64 and shoff+count*64<=len(elf),'ELF_SECTIONS_INVALID')
    sections=[struct.unpack_from('<IIQQQQIIQQ',elf,shoff+i*64) for i in range(count)]
    wanted={**{name:(offset,size) for name,(offset,size,_) in FUNCTIONS.items()},
            'heap_base':(0x134368,8),'heap_limit':(0x134370,8)}
    found={name:[] for name in wanted}
    for sec in sections:
        if sec[1]!=2:continue
        names=sections[sec[6]];strings=elf[names[4]:names[4]+names[5]]
        require(sec[9]==24,'ELF_SYMBOL_STRIDE_DIFFERS')
        for off in range(sec[4],sec[4]+sec[5],24):
            name,_,_,_,value,size=struct.unpack_from('<IBBHQQ',elf,off)
            text=strings[name:strings.find(b'\0',name)].decode()
            if text in found:found[text].append((value,size))
    require(all(found[name]==[span] for name,span in wanted.items()),'ELF_ALLOCATOR_SYMBOLS_DIFFER')
    for name,(offset,size,sha) in FUNCTIONS.items():
        require(digest(flat[offset:offset+size])==sha,'FLAT_FUNCTION_BYTES_DIFFER')
        code=[sec for sec in sections if sec[1]==1 and sec[2]&6==6 and sec[3]<=offset and offset+size<=sec[3]+sec[5]]
        require(len(code)==1,'ELF_CODE_EXTENT_AMBIGUOUS')
        sec=code[0];start=sec[4]+offset-sec[3]
        require(elf[start:start+size]==flat[offset:offset+size],'ELF_FLAT_CODE_DIFFERS')
        rows=[r for r in evidence['functions'] if r['symbol']==name]
        require(len(rows)==1 and (rows[0]['offset'],rows[0]['bytes'],rows[0]['sha256'])==(offset,size,sha),'INSTRUCTION_EXTENTS_DIFFER')
    module=types.ModuleType('pinned_staging_geometry')
    exec(compile(inputs['planner'],'pinned-planner.py','exec',dont_inherit=True,optimize=0),module.__dict__)
    return module


def allocation_math(raw_heap,size,upper,heap_limit):
    require(all(type(v) is int and 0<=v<=U64 for v in (raw_heap,size,upper,heap_limit)),'INVALID_ALLOCATION_INTEGER')
    require(raw_heap>0 and raw_heap<=U64-63,'ALIGN64_OVERFLOW')
    block=(raw_heap+63)&~63
    require(size>0 and size<=U64-block,'ALLOCATION_OVERFLOW')
    result=block+size
    require(result<=upper and (heap_limit==0 or result<=heap_limit),'ALLOCATION_END_EXCEEDS_BOUND')
    return block,result


def plan_private(capture_bytes,expected_pins,*,binary_inputs=None,container_sha256,
                 container_length,bootargs_bytes,bootargs_sha256,expected_raw_heap):
    """PRIVATE addresses. Geometry only; root must independently verify the bundle.

    bootargs_bytes/hash identify ORIGINAL session bytes, not final child payload.
    Caller must patch only top_of_kernel_data to child_end and verify that delta.
    Source/binary contract permits ONLY heap_base's bookkeeping store (and stack
    accesses). Skipped vendor extents are not writable and are not child-owned.
    """
    m=verify_binary_contract(binary_inputs)
    c,protected,counts=m._capture(capture_bytes,expected_pins)
    require(type(container_sha256) is str and len(container_sha256)==64 and all(x in '0123456789abcdef' for x in container_sha256),'CONTAINER_HASH_REQUIRED')
    require(type(container_length) is int and 0<container_length<(32<<20),'CONTAINER_EXCEEDS_SEPARATE_LAYOUT')
    require(digest(bootargs_bytes)==bootargs_sha256==c['session']['bootargs_sha256'] and len(bootargs_bytes)==1152,'ORIGINAL_BOOTARGS_DIFFERS')
    memory=c['memory'];raw=memory['heap_base'];upper=memory['usable_base']+memory['usable_size']
    require(type(expected_raw_heap) is int and expected_raw_heap==raw,'EXPECTED_HIGH_WATER_DIFFERS')
    if memory['heap_limit']:upper=min(upper,memory['heap_limit'])
    child=m.choose_base(max(raw,memory['bootargs_top'],memory['resident_end']),64<<20,upper,protected)
    end=child+(64<<20);block=(raw+63)&~63;size=end-block
    require(all(not m.overlaps(child,end,lo,hi) for lo,hi in protected),'FINAL_CHILD_OVERLAPS_PROTECTED')
    require(child<=child+0x800<child+container_length and child+container_length<=child+(32<<20),'PIC_OR_CONTAINER_OUTSIDE_CHILD')
    require(child+(32<<20)+len(bootargs_bytes)<=end,'BOOTARGS_OUTSIDE_CHILD')
    returned,result=allocation_math(raw,size,upper,memory['heap_limit'])
    require(returned==block and result==end,'ALLOCATOR_RESULT_DIFFERS')
    return dict(schema=1,status='PRIVATE_NONWRITING_GEOMETRY_ONLY',hardware='UNTESTED',
      capture_sha256=expected_pins['capture_sha256'],binary_contract=dict(PINS),
      container_sha256=container_sha256,container_length=container_length,
      original_bootargs_sha256=bootargs_sha256,raw_heap=raw,aligned_heap=block,
      required_bootargs_delta=dict(field='top_of_kernel_data',old=memory['bootargs_top'],new=end,other_fields='UNCHANGED'),
      final_bootargs_payload='NOT_CONSTRUCTED_OR_VERIFIED',
      allocation_bytes=size,expected_allocation_return=block,expected_heap_after=end,
      child_base=child,child_bytes=64<<20,pic_entry=child+0x800,
      container_destination=child,bootargs_destination=child+(32<<20),
      skipped_ranges_writable=False,reservation_claimed=False,deployment_authorized=False,
      target_actions=False,bundle_validity='CALLER_MUST_INDEPENDENTLY_VERIFY',
      cpu_state=dict(c['cpu_state']),range_counts=counts,
      remaining_gates=['LIVE_RECHECK','EXCLUSIVE_ALLOCATOR_OWNERSHIP','CPU_WFE_READINESS',
                       'BUNDLE_VERIFICATION','SUPERVISED_RECOVERY','SEPARATE_STAGER_REVIEW'])
