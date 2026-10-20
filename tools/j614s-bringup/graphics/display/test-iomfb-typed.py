#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Causal regression using actual D006 types, handler, trampoline and receive code."""
import argparse, hashlib, json, os, re, subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
p.add_argument('--cc',default='clang');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
BASE='8e27e3edbf57903da4d62ab52f3b77df23801772'
functions=('dcp_tx_offset','dcp_channel_offset','dcp_get_channel','dcp_push_depth','dcp_pop_depth','dcp_parse_tag','dcpep_handle_cb','dcpep_handle_ack','dcpep_got_msg')
def function(source,name):
 m=re.search(r'\b'+name+r'\([^;{]*?\)\n\{',source)
 if not m:raise ValueError('missing function '+name)
 start=source.rfind('\nstatic ',0,m.start())+1 if not source[m.start()-1:m.start()].isalnum() else -1
 # Nonstatic dcp_parse_tag has its own preceding declaration line.
 if name=='dcp_parse_tag':start=source.rfind('\nint ',0,m.start())+1
 brace=source.index('{',m.start());depth=1;i=brace+1
 while depth:depth+=(source[i]=='{')-(source[i]=='}');i+=1
 if start<0 or start>m.start():raise ValueError('function start')
 return source[start:i]+'\n'
def read(name,baseline):
 path='drivers/gpu/drm/apple/'+name
 return subprocess.check_output(['git','-C',str(a.source),'show',BASE+':'+path],text=True) if baseline else (a.source/path).read_text()
def structure(source,name):
 m=re.search(r'struct '+name+r' \{.*?\} __packed;',source,re.S)
 if not m:raise ValueError('missing struct '+name)
 return m.group()+'\n'
results=[]
for name,baseline in [('baseline',True),('candidate',False)]:
 out=a.output/name;out.mkdir(exist_ok=True)
 source=read('iomfb.c',baseline);h=read('iomfb.h',baseline);internal=read('dcp-internal.h',baseline)
 declarations=h[h.index('/* Fixed size'):h.index('enum iomfb_property_id')]
 declarations+='\n'+re.search(r'^#define IOMFB_MAX_CB[^\n]*',h,re.M).group()+'\n'
 declarations+='\n'+internal[internal.index('#define DCP_MAX_CALL_DEPTH'):internal.index('/* Already warned')]+'bool warned_busy;\n};\n'
 declarations=declarations.replace('typedef void (*dcp_callback_t)(struct apple_dcp *, void *, void *);','')
 contract=re.search(r'struct iomfb_cb_contract \{.*?\};',h,re.S)
 declarations+='\ntypedef bool (*iomfb_cb_handler)(struct apple_dcp *, int, void *, void *);\n'
 if contract:declarations+='\n'+contract.group()+'\n'
 (out/'iomfb-declarations.inc').write_text(declarations)
 prefix=Path(__file__).with_name('iomfb-host-test.c').read_text().split('#include "iomfb-functions.inc"')[0]
 # Candidate metadata pointer is host structure shape, not state logic.
 # Prefix already includes the metadata pointer; baseline never accesses it.
 (out/'iomfb-host-prefix.inc').write_text(prefix)
 (out/'iomfb-packet.h').write_text(read('iomfb-packet.h',baseline))
 (out/'iomfb-functions.inc').write_text('#include "iomfb-packet.h"\n'+'\n'.join(function(source,f) for f in functions))
 v26=read('iomfb_v26_6.h',baseline);template=read('iomfb_template.c',baseline);macros=read('iomfb_internal.h',baseline)
 m=re.search(r'#define TRAMPOLINE_INOUT\(.*?(?=\n#define)',macros,re.S)
 if not m:raise ValueError('typed macro missing')
 typed=structure(v26,'dcp_set_frame_sync_props_req_v26_6_0')+structure(v26,'dcp_set_frame_sync_props_resp_v26_6_0')
 size_macro=re.search(r'#define DCP_CB_SIZE\(.*?(?=\n#define)',macros,re.S)
 if size_macro:typed+=size_macro.group()+'\n'
 typed+=m.group()+'\n'+function(template,'dcpep_cb_set_frame_sync_props')
 invocation=re.search(r'TRAMPOLINE_INOUT\(trampoline_set_frame_sync_props,\s*dcpep_cb_set_frame_sync_props,\s*struct dcp_set_frame_sync_props_req_v26_6_0,\s*struct dcp_set_frame_sync_props_resp_v26_6_0\);',template)
 typed+=invocation.group()+'\n'
 (out/'iomfb-typed-callback.inc').write_text(typed)
 contract_setup=''
 if contract:
  contract_setup='static const struct iomfb_cb_contract contracts[1000] = { [6] = { trampoline_set_frame_sync_props, trampoline_set_frame_sync_props_in_size, trampoline_set_frame_sync_props_out_size } }; dcp.cb_contracts=contracts;\n'
 (out/'iomfb-typed-contract.inc').write_text(contract_setup)
 executable=(out/'typed-test').resolve()
 command=[a.cc,'-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(out.resolve()),str(Path(__file__).with_name('iomfb-typed-host-test.c').resolve()),'-o',str(executable)]
 compile=subprocess.run(command,capture_output=True,text=True);(out/'compile.log').write_text(compile.stdout+compile.stderr)
 if compile.returncode:raise SystemExit(name+' compile failed: '+compile.stderr)
 env=dict(os.environ,ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1')
 run=subprocess.run([str(executable)]+(['--expect-baseline-bug'] if baseline else []),capture_output=True,text=True,env=env)
 (out/'run.log').write_text(run.stdout+run.stderr)
 if run.returncode:raise SystemExit(name+' run failed: '+run.stdout+run.stderr)
 failure=None
 if baseline:
  strict=subprocess.run([str(executable)],capture_output=True,text=True,env=env)
  (out/'fixed-invariant.log').write_text(strict.stdout+strict.stderr)
  if strict.returncode!=1 or 'typed short input must reject' not in strict.stderr:raise SystemExit('wrong baseline failure')
  failure={'exit':strict.returncode,'message':strict.stderr.splitlines()[0]}
 results.append({'name':name,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'typed_handler_sha256':hashlib.sha256(typed.encode()).hexdigest(),'output':run.stdout.splitlines(),'compile_exit':compile.returncode,'run_exit':run.returncode,'fixed_invariant_failure':failure})
result={'scope':'Actual D006 handler/types/TRAMPOLINE_INOUT and actual receive functions, host Linux boundaries','baseline_commit':BASE,'hardware_tested':False,'runs':results}
(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
