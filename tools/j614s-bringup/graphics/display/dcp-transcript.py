#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline only: validate bounded IOMFB CALL/ACK logs from the public m1n1 tracer.

No source import, live device, DART walk, GPU/DCP RPC, reset or mailbox access.
Unrecognised application contracts remain explicit, even for a valid envelope.
"""
import argparse, ctypes, hashlib, json, re, subprocess
from pathlib import Path

BASE = 'db9f2f8f00986e3ef03fddbdaad55a861e793123'
FW = 'bc99f51f7b117a2af77198c061e440c7cc8232f04799ab0a53979e55c03ed925'
DCP_VERSION = 'AppleDCP-1041.120.7~2715-t604xdcp.RELEASE'
# These are source contracts, not an assertion that T6040 implements them.
# Each non-scalar size is checked against a retained source static_assert.
SHAPES = {
 'D006': ('dcp_set_frame_sync_props_req_v26_6_0','dcp_set_frame_sync_props_resp_v26_6_0',84,80),
 'D114': ('dcp_dict_passthrough_req_v26_6','dcp_dict_passthrough_resp_v26_6',0x1044,0x1004),
 'D575': ('dcp_hotplug_req_v26_6','dcp_hotplug_resp_v26_6',0x58,0x4c),
 'D590': ('dc_swap_complete_resp_v26_6_0',None,0x730,0),
 'D592': ('dcp_swap_complete_intent_gated_v26_6',None,0x14,0),
 'A406': ('dcp_swap_start_req_v26_6_0','dcp_swap_start_resp_v26_6_0',0x10,8),
 'A407': ('dcp_swap_submit_req_v26_6_0','dcp_swap_submit_resp_v26_6_0',0x1bd8,12),
}
CHANNELS = {
 ('>','CALL',0):'CMD', ('>','CALL',2):'CMD',
 ('>','CALL',4):'OOBCMD', ('>','CALL',6):'OOBCMD',
 ('<','CALL',0):'CB', ('<','CALL',3):'ASYNC',
 ('<','CALL',4):'OOBCB', ('<','CALL',7):'OOBASYNC',
 ('<','ACK',0):'CMD', ('<','ACK',2):'CMD',
 ('<','ACK',4):'OOBCMD', ('<','ACK',6):'OOBCMD',
 ('>','ACK',0):'CB', ('>','ACK',3):'ASYNC',
 ('>','ACK',4):'OOBCB', ('>','ACK',7):'OOBASYNC',
}
class DecodeError(ValueError): pass

def integer(value, maximum=0xffffffff):
 try: n=int(value,0)
 except (ValueError,TypeError): raise DecodeError('invalid integer') from None
 if n<0 or n>maximum: raise DecodeError('integer outside allowed range')
 return n

def contracts(source):
 text=(source/'drivers/gpu/drm/apple/iomfb_v26_6.c').read_text()
 sizes={name:int(size,0) for name,size in re.findall(r'static_assert\(sizeof\(struct (\w+)\) == (0x[0-9a-f]+|[0-9]+)\)',text)}
 handlers={f'D{int(n):03}':name for n,name in re.findall(r'\[(\d+)\] = (\w+)',text)}
 handlers.update({f'D{int(n):03}':name for n,name in re.findall(r'^\s*CB\((\d+),\s*(\w+)\),',text,re.M)})
 expected_handlers={'D006':'trampoline_set_frame_sync_props','D114':'trampoline_passthrough_dict_v26_6',
                    'D575':'trampoline_hotplug','D590':'trampoline_swap_complete',
                    'D592':'trampoline_swap_complete_intent_gated'}
 for tag,name in expected_handlers.items():
  if handlers.get(tag)!=name: raise DecodeError('source callback mapping changed: '+tag)
 if 'IOMFB_METHOD("A406", dcpep_swap_start)' not in text or 'IOMFB_METHOD("A407", dcpep_swap_submit)' not in text:
  raise DecodeError('source swap method mapping changed')
 for tag,(req,resp,i,o) in SHAPES.items():
  if sizes.get(req)!=i or (resp is not None and sizes.get(resp)!=o):
   raise DecodeError('source size assertion changed: '+tag)
 return handlers

def bridge(source,output,cc='clang'):
 output.mkdir(parents=True,exist_ok=True)
 library=output/'envelope.so'
 subprocess.run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-fPIC','-shared',
  '-I',str(source/'drivers/gpu/drm/apple'),str(Path(__file__).with_name('iomfb-envelope-bridge.c')),
  '-o',str(library)],check=True,capture_output=True,text=True)
 lib=ctypes.CDLL(str(library.resolve()))
 fn=lib.display_packet_valid;fn.argtypes=[ctypes.c_uint32]*4;fn.restype=ctypes.c_int
 return fn

def check_identity(metadata):
 expected={'chip_id':'0x6040','model':'Mac16,8','os_build':'25G83',
           'dcp_payload_sha256':FW,'dcp_build':DCP_VERSION}
 for k,v in expected.items():
  if metadata.get(k)!=v: raise DecodeError('capture identity not exact: '+k)
 # Sidecar identity is supplied evidence, never proof of the image actually loaded.
 return 'Caller-supplied provenance; actual loaded firmware and capture coherence require independent qualification'

def decode(lines,metadata,handlers,valid):
 provenance=check_identity(metadata)
 pending={}; summary=[]; unknown=[]; packets=0
 for line_no,line in enumerate(lines,1):
  if len(line)>2*0x8000+512: raise DecodeError('trace line exceeds channel bound')
  if line.startswith('CALL '):
   fields=line.rstrip('\r\n').split(' ',8)
   if len(fields)!=9: raise DecodeError('CALL field count')
   kind,direction,wire,channel,off,tag,ins,outs,data=fields
  elif line.startswith('ACK '):
   fields=line.rstrip('\r\n').split(' ',5)
   if len(fields)!=6: raise DecodeError('ACK field count')
   kind,direction,wire,channel,off,data=fields
  else: raise DecodeError('unrecognised record (no implicit version override)')
  word=integer(wire,0xffffffffffffffff); offset=integer(off,0xffff)
  ctx=(word>>8)&15;wire_off=(word>>16)&0xffff;length=word>>32
  ack=bool(word&64)
  if (word&15)!=2 or ack!=(kind=='ACK'): raise DecodeError('message type/ACK flag mismatch')
  if CHANNELS.get((direction,kind,ctx))!=channel: raise DecodeError('context/channel/direction mismatch')
  try: body=bytes.fromhex(data)
  except ValueError: raise DecodeError('invalid payload hex') from None
  # Whitespace and odd input must not be silently normalised.
  if data!=body.hex(): raise DecodeError('noncanonical/truncated payload hex')
  stack=pending.setdefault(channel,[])
  if kind=='CALL':
   i=integer(ins);o=integer(outs)
   if wire_off!=offset or not valid(offset,length,i,o): raise DecodeError('invalid bounded IOMFB envelope')
   if len(body)!=i: raise DecodeError('input capture truncated')
   if len(stack)>=8: raise DecodeError('source call-depth bound exceeded')
   if stack and offset<stack[-1]['aligned_end']: raise DecodeError('overlapping nested packets')
   if not re.fullmatch(('A' if direction=='>' else 'D')+r'\d{3}',tag): raise DecodeError('tag direction mismatch')
   row={'line':line_no,'tag':tag,'input':i,'output':o,'channel':channel,
        'envelope':'VALID','complete':False,'offset':offset,
        'aligned_end':offset+((length+63)&~63)}
   shape=SHAPES.get(tag)
   if shape is not None:
    row['source_contract']='MATCH' if (i,o)==shape[2:] else 'MISMATCH'
   else: row['source_contract']='UNDECODED'
   if row['source_contract']!='MATCH':
    reason='shape not yet decoded'
    if tag.startswith('D') and tag not in handlers: reason='no handler in selected26.6 source'
    if row['source_contract']=='MISMATCH': reason='captured lengths differ from selected source contract'
    unknown.append({'line':line_no,'tag':tag,'input':i,'output':o,'reason':reason})
   summary.append(row);stack.append(row)
  else:
   if length or wire_off: raise DecodeError('ACK unexpectedly contains packet range')
   if not stack or stack[-1]['offset']!=offset: raise DecodeError('orphan or reordered ACK')
   row=stack[-1]
   if len(body)!=row['output']: raise DecodeError('output capture truncated')
   row['complete']=True;stack.pop()
  packets+=1
 unclosed=sum(len(s) for s in pending.values())
 return {'scope':'Offline transcript envelope/source-contract comparison only',
         'status':'PARTIAL' if unknown or unclosed else 'WORKS_OFFLINE_SUBSET_ONLY',
         'hardware_tested':False,'safe_to_enable_t6040_dcp':False,
         'capture_provenance':provenance,'packets':packets,'incomplete_calls':unclosed,
         'first_unsupported_contract':unknown[0] if unknown else None,
         'unsupported_contracts':unknown,'calls':summary}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
 p.add_argument('--metadata',type=Path,required=True);p.add_argument('--transcript',type=Path,required=True)
 p.add_argument('--scratch',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args()
 try:
  # Streaming cap applies before allocating a complete transcript.
  if a.transcript.stat().st_size>64*1024*1024: raise DecodeError('trace exceeds explicit offline cap')
  with a.transcript.open() as f: result=decode(f,json.loads(a.metadata.read_text()),contracts(a.source),bridge(a.source,a.scratch))
 except (DecodeError,OSError,json.JSONDecodeError,subprocess.CalledProcessError) as e: p.exit(1,str(e)+'\n')
 result['source_commit']=subprocess.check_output(['git','-C',str(a.source),'rev-parse','HEAD'],text=True).strip()
 result['source_header_sha256']=hashlib.sha256((a.source/'drivers/gpu/drm/apple/iomfb-packet.h').read_bytes()).hexdigest()
 result['transcript_sha256']=hashlib.sha256(a.transcript.read_bytes()).hexdigest()
 a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
