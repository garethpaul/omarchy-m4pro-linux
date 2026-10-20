#!/usr/bin/env python3
"""Bounded ELF64 little-endian static contracts. No dynamic loading/execution."""
import struct

def parse_elf(data):
    def span(offset,size):
        if offset<0 or size<0 or offset>len(data) or size>len(data)-offset:raise ValueError('ELF extent outside file')
        return data[offset:offset+size]
    def unpack(fmt,offset):
        return struct.unpack(fmt,span(offset,struct.calcsize(fmt)))
    if len(data)<64 or data[:6]!=b'\x7fELF\x02\x01':raise ValueError('requires complete ELF64 little-endian header')
    typ,machine=unpack('<HH',16);shoff=unpack('<Q',40)[0];ehsize,phentsize,phnum,shentsize,shnum,shstrndx=unpack('<HHHHHH',52)
    if ehsize!=64 or shentsize!=64 or not shoff or not shnum or shstrndx>=shnum:raise ValueError('unsupported/missing ELF section table')
    span(shoff,shnum*shentsize)
    sections=[unpack('<IIQQQQIIQQ',shoff+i*64) for i in range(shnum)]
    def contents(section):return span(section[4],section[5])
    names=contents(sections[shstrndx])
    def string(buf,off):
        if off>=len(buf):raise ValueError('string offset outside table')
        end=buf.find(b'\0',off)
        if end<0:raise ValueError('unterminated ELF string')
        return bytes(buf[off:end]).decode('utf-8','strict')
    byname={string(names,s[0]):s for s in sections}
    out={'class':64,'endian':'little','machine':machine,'type':typ,'needed':[],'soname':None,'rpath':[],'runpath':[],
         'version_requirements':{},'version_definitions':[],'versioned_imports':[],'exports':[],'undefined':[]}
    dynamic=byname.get('.dynamic')
    if dynamic:
        if dynamic[6]>=shnum or dynamic[9]!=16 or dynamic[5]%16:raise ValueError('bad dynamic section')
        strings=contents(sections[dynamic[6]])
        for off in range(dynamic[4],dynamic[4]+dynamic[5],16):
            tag,value=unpack('<qQ',off)
            if tag==0:break
            if tag in (1,14,15,29):
                value=string(strings,value)
                if tag==1:out['needed'].append(value)
                elif tag==14:out['soname']=value
                else:out['rpath' if tag==15 else 'runpath']=value.split(':')
    indices={};need=byname.get('.gnu.version_r')
    if need:
        buf=contents(need);strings=contents(sections[need[6]]);off=0;seen=set()
        while True:
            if off in seen or off+16>len(buf):raise ValueError('bad version need chain')
            seen.add(off);version,count,file,aux,nxt=struct.unpack_from('<HHIII',buf,off)
            if version!=1:raise ValueError('unsupported version need format')
            filename=string(strings,file);requirements=[];a=off+aux;aseen=set()
            for _ in range(count):
                if a in aseen or a+16>len(buf):raise ValueError('bad version auxiliary chain')
                aseen.add(a);hash_,flags,index,name,anext=struct.unpack_from('<IHHII',buf,a)
                name=string(strings,name);indices[index & 0x7fff]=(filename,name,flags);requirements.append(name);a+=anext
            out['version_requirements'][filename]=sorted(set(requirements))
            if not nxt:break
            off+=nxt
    definitions={};definition=byname.get('.gnu.version_d')
    if definition:
        buf=contents(definition);strings=contents(sections[definition[6]]);off=0;seen=set()
        while True:
            if off in seen or off+20>len(buf):raise ValueError('bad version definition chain')
            seen.add(off);version,flags,index,count,hash_,aux,nxt=struct.unpack_from('<HHHHIII',buf,off)
            if version!=1 or not count or off+aux+8>len(buf):raise ValueError('bad version definition')
            name,anext=struct.unpack_from('<II',buf,off+aux);definitions[index & 0x7fff]=string(strings,name)
            if not nxt:break
            off+=nxt
        out['version_definitions']=sorted(set(definitions.values()))
    symbols=byname.get('.dynsym');versions=byname.get('.gnu.version')
    if symbols:
        if symbols[9]!=24 or symbols[5]%24 or symbols[6]>=shnum:raise ValueError('bad dynamic symbols')
        strings=contents(sections[symbols[6]]);count=symbols[5]//24
        vbuf=contents(versions) if versions else None
        if vbuf is not None and len(vbuf)<count*2:raise ValueError('short symbol versions')
        for i in range(count):
            name,info,other,shndx,value,size=unpack('<IBBHQQ',symbols[4]+i*24)
            if not name:continue
            name=string(strings,name);bind=info>>4;visibility=other & 3
            index=(struct.unpack_from('<H',vbuf,i*2)[0] & 0x7fff) if vbuf is not None else 1
            if shndx==0:
                out['undefined'].append({'name':name,'weak':bind==2})
                if index in indices:
                    filename,version,flags=indices[index]
                    out['versioned_imports'].append({'name':name,'version':version,'file':filename,'weak':bind==2,'version_weak':bool(flags&2)})
            elif bind in (1,2,10) and visibility in (0,3):
                out['exports'].append({'name':name,'version':definitions.get(index)})
    return out

def check_edge(consumer,provider,needed):
    """Exact provider's version nodes/symbols only; not complete runtime symbol scope."""
    issues=[]
    if any(consumer[k]!=provider[k] for k in ('class','endian','machine')):issues.append('architecture_mismatch')
    definitions=set(provider['version_definitions']);exports={(s['name'],s['version']) for s in provider['exports']}
    for version in consumer['version_requirements'].get(needed,[]):
        if version not in definitions:issues.append('missing_version:'+version)
    for symbol in consumer['versioned_imports']:
        if symbol['file']==needed and not symbol['weak'] and (symbol['name'],symbol['version']) not in exports:
            issues.append('missing_symbol:'+symbol['name']+'@'+symbol['version'])
    return sorted(set(issues))

def check_scope(consumer,provider,needed,scope,available=None):
    """Versioned imports may be exported by another loaded dependency (e.g. libc)."""
    issues=check_edge(consumer,provider,needed)
    if available is None:
        available={s['name']+'@'+str(s['version']) for elf in [provider]+scope
                   if all(elf[k]==consumer[k] for k in ('class','endian','machine'))
                   for s in elf['exports']}
    return [issue for issue in issues if not (issue.startswith('missing_symbol:') and issue.removeprefix('missing_symbol:') in available)]
