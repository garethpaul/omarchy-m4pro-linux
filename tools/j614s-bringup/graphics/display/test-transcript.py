#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import argparse, importlib.util, json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--scratch',type=Path,required=True);a=p.parse_args()
spec=importlib.util.spec_from_file_location('dcp_transcript',Path(__file__).with_name('dcp-transcript.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
handlers=m.contracts(a.source);valid=m.bridge(a.source,a.scratch)
meta={'chip_id':'0x6040','model':'Mac16,8','os_build':'25G83','dcp_payload_sha256':m.FW,'dcp_build':m.DCP_VERSION}
def word(ctx,off,length,ack=False):return hex(2|(ctx<<8)|(off<<16)|(length<<32)|(64 if ack else 0))
def call(tag='D006',i=84,o=80,off=0,ctx=0,channel='CB',direction='<',length=None):
 return f'CALL {direction} {word(ctx,off,12+i+o if length is None else length)} {channel} {hex(off)} {tag} {hex(i)} {hex(o)} '+bytes(i).hex()+'\n'
def ack(o=80,off=0,ctx=0,channel='CB',direction='>'):
 return f'ACK {direction} {word(ctx,0,0,True)} {channel} {hex(off)} '+bytes(o).hex()+'\n'
def decode(lines,metadata=meta):return m.decode(lines,metadata,handlers,valid)
tests=[]
def good(name,fn):fn();tests.append(name)
def rejects(name,lines,metadata=meta):
 try:decode(lines,metadata)
 except m.DecodeError:tests.append(name);return
 raise AssertionError(name+' did not reject')
r=decode([call(),ack()]);assert r['packets']==2 and not r['first_unsupported_contract'] and not r['safe_to_enable_t6040_dcp'];tests.append('source-shaped callback/ACK envelope only')
r=decode([call(i=80),ack()]);assert r['first_unsupported_contract']['reason']=='captured lengths differ from selected source contract';tests.append('changed D006 shape flagged, not falsely passed')
r=decode([call(tag='D999',i=0,o=0),ack(o=0)]);assert 'no handler' in r['first_unsupported_contract']['reason'];tests.append('missing callback identified precisely')
rejects('short wire header',[call(i=0,o=0,length=11)])
rejects('envelope length mismatch',[call(length=12)])
rejects('channel overrun',[call(off=0x7fc0)])
rejects('orphan ACK',[ack()])
rejects('truncated input capture',[call()[:-3]+'\n'])
rejects('truncated output capture',[call(),ack(o=79)])
rejects('context/channel mismatch',[call(ctx=3)])
rejects('overlapping nested packets',[call(),call()])
rejects('wrong exact firmware identity',[call()],dict(meta,os_build='25G72'))
rejects('version records do not override identity',['VERSION V:V26_6\n'])
r=decode([call()]);assert r['incomplete_calls']==1 and r['status']=='PARTIAL';tests.append('incomplete capture remains partial')
print(json.dumps({'status':'PASS_OFFLINE_SYNTHETIC_ONLY','tests':tests,'count':len(tests),'hardware_tested':False},indent=2))
