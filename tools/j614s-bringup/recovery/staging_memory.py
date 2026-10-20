# SPDX-License-Identifier: MIT
"""Pure decoding of private ADT and allocator observations; no target API."""
import struct

U64=1 << 64
SOURCES=('/chosen/memory-map','/chosen/carveout-memory-map')

def require(condition,message):
    if not condition:raise ValueError(message)

def integer(value):
    return type(value) is int and 0 <= value < U64

def span(base,size):
    return integer(base) and integer(size) and size>0 and base+size<U64

def decode_ranges(sections):
    require(type(sections) is dict and set(sections)==set(SOURCES),'Exact ADT source sections required')
    rows=[]
    for source in SOURCES:
        require(type(sections[source]) is list and len(sections[source]) <= 4096,'Invalid ADT property list')
        seen=set()
        for name,value in sections[source]:
            require(type(name) is str and name and len(name)<=128 and '\0' not in name,'Invalid ADT property name')
            require(name not in seen,'Duplicate ADT property name');seen.add(name)
            require(type(value) is bytes,'Invalid raw ADT property bytes')
            if len(value)!=16:continue
            base,size=struct.unpack('<QQ',value)
            require((base,size)==(U64-1,U64-1) or base+size<U64,'ADT range overflow')
            rows.append(dict(source=source,name=name,raw_hex=value.hex(),base=base,size=size))
    require(rows,'No ADT ranges observed')
    return rows

def validate_heap(memory, metadata):
    keys=('usable_base','usable_size','resident_base','resident_end','heap_base','heap_limit','bootargs_top')
    require(all(integer(memory[k]) for k in keys),'Invalid allocator integer')
    base,size=memory['usable_base'],memory['usable_size'];end=base+size
    require(span(base,size),'Invalid usable RAM extent')
    require(base<=memory['resident_base']<memory['resident_end']<=memory['bootargs_top']<=memory['heap_base']<=end,'Invalid resident/top/heap ordering')
    require(memory['heap_limit']==0 or memory['heap_base']<=memory['heap_limit']<=end,'Invalid allocator limit')
    require(type(metadata) is list and len(metadata)==2 and {r['name'] for r in metadata}=={'live-bootargs','live-adt'},'Exact protected metadata required')
    for row in metadata:
        require(span(row['base'],row['size']) and base<=row['base']<row['base']+row['size']<=end,'Protected metadata outside usable RAM')
