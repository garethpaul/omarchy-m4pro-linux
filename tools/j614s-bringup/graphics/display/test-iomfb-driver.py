#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build actual pinned driver receive functions with host boundary replacements."""
import argparse, hashlib, json, os, re, subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,required=True)
p.add_argument('--baseline',default='db9f2f8f00986e3ef03fddbdaad55a861e793123')
p.add_argument('--output',type=Path,required=True)
p.add_argument('--cc',default='clang')
a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=True)
functions=('dcp_tx_offset','dcp_channel_offset','dcp_get_channel','dcp_push_depth','dcp_pop_depth','dcp_parse_tag','dcpep_handle_cb','dcpep_handle_ack','dcpep_got_msg')
def extract_function(source,name):
 m=re.search(r'^(?:static )?(?:inline )?[^\n]+\b'+name+r'\([^;]*?\)\n\{',source,re.M)
 if not m: raise ValueError('Cannot find function '+name)
 start=m.start(); brace=m.end()-1; depth=1; i=brace+1
 while depth:
  depth+=(source[i]=='{')-(source[i]=='}'); i+=1
 return source[start:i]+'\n'
def read(name,baseline):
 path='drivers/gpu/drm/apple/'+name
 if baseline: return subprocess.check_output(['git','-C',str(a.source),'show',a.baseline+':'+path],text=True)
 return (a.source/path).read_text()
results=[]
for name,baseline in [('baseline',True),('candidate',False)]:
 out=a.output/name;out.mkdir(exist_ok=True)
 source=read('iomfb.c',baseline); h=read('iomfb.h',baseline); internal=read('dcp-internal.h',baseline)
 declarations=h[h.index('/* Fixed size'):h.index('enum iomfb_property_id')]
 declarations+='\n'+re.search(r'^#define IOMFB_MAX_CB[^\n]*',h,re.M).group()+'\n'
 declarations+='\n'+internal[internal.index('#define DCP_MAX_CALL_DEPTH'):internal.index('/* Already warned')]+ 'bool warned_busy;\n};\n'
 # Callback typedef is already above the extracted channel declarations.
 declarations=declarations.replace('typedef void (*dcp_callback_t)(struct apple_dcp *, void *, void *);','')
 contract=re.search(r'struct iomfb_cb_contract \{.*?\};',h,re.S)
 if contract:
  declarations+='\ntypedef bool (*iomfb_cb_handler)(struct apple_dcp *, int, void *, void *);\n'+contract.group()+'\n'
 else:
  declarations+='\ntypedef bool (*iomfb_cb_handler)(struct apple_dcp *, int, void *, void *);\n'
 (out/'iomfb-declarations.inc').write_text(declarations)
 (out/'iomfb-functions.inc').write_text('\n'.join(extract_function(source,f) for f in functions))
 if not baseline:
  for inc in re.findall(r'#include "(iomfb-packet.h)"',source):
   (out/inc).write_text(read(inc,False))
  if 'iomfb-packet.h' in source:
   (out/'iomfb-functions.inc').write_text('#include "iomfb-packet.h"\n'+(out/'iomfb-functions.inc').read_text())
 command=[a.cc,'-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(out.resolve()),str(Path(__file__).with_name('iomfb-host-test.c').resolve()),'-o',str((out/'test').resolve())]
 compile=subprocess.run(command,capture_output=True,text=True);(out/'compile.log').write_text(compile.stdout+compile.stderr)
 if compile.returncode: raise SystemExit(name+' compile failed: '+compile.stderr)
 env=dict(os.environ,ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1')
 run=subprocess.run([str((out/'test').resolve())]+(['--expect-baseline-bug'] if baseline else []),capture_output=True,text=True,env=env)
 (out/'run.log').write_text(run.stdout+run.stderr)
 if run.returncode: raise SystemExit(name+' run failed: '+run.stdout+run.stderr)
 strict=None
 if baseline:
  before=subprocess.run([str((out/'test').resolve())],capture_output=True,text=True,env=env)
  (out/'fixed-invariant.log').write_text(before.stdout+before.stderr)
  if before.returncode!=1 or 'malformed callback must be rejected' not in before.stderr: raise SystemExit('Baseline did not fail the intended invariant')
  strict={'exit':before.returncode,'diagnosis':before.stderr.splitlines()[0]}
 results.append({'name':name,'iomfb_c_sha256':hashlib.sha256(source.encode()).hexdigest(),'compile_exit':compile.returncode,'run_exit':run.returncode,'output':run.stdout.splitlines(),'fixed_invariant':strict})
result={'candidate_commit':subprocess.check_output(['git','-C',str(a.source),'rev-parse','HEAD'],text=True).strip(),'compiler':subprocess.check_output([a.cc,'--version'],text=True).splitlines()[0],'harness_sha256':hashlib.sha256(Path(__file__).with_name('iomfb-host-test.c').read_bytes()).hexdigest(),'scope':'Actual kernel receive-function bodies; fake Linux boundary only. No target or firmware execution.','hardware_tested':False,'baseline_commit':a.baseline,'runs':results}
(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
