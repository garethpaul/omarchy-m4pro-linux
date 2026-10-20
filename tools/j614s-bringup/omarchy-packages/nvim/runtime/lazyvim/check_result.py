#!/usr/bin/env python3
"""Independent expectations over the actual full-loader observation and logs."""
import argparse
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
EXPECTED={
 'shell':('shfmt',['if true; then echo arm64; fi']),
 'lua':('stylua',['local x = { 1, 2 }','return x']),
}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def check(work):
 r=json.loads((work/'result.json').read_text());o=json.loads((work/'scratch/observations.json').read_text())
 assert r['exit']==0 and r['timed_out'] is False
 assert r['runner_sha256']==sha(HERE/'run_startup.py') and r['probe_sha256']==sha(HERE/'probe.lua')
 assert r['formatter_ELF_machine']==183
 assert r['host_interpreter_path_sha256']==r['qemu_sha256']=='66bdc286fd30970a1c3d2029b460605a3dc843ed6b397f4cd9825f9c19551507'
 assert r['formatter_files']=={'shfmt':'ebe5ee1d142c2dac3efff9adced24c8f491734e724d0316141bcecae1a684108','stylua':'3618e5a684446a15ae15bc18b1168ed1564eec037f82295de80e5e0176679007'}
 for name,checksum in r['formatter_files'].items():assert sha(work/'root/usr/bin'/name)==checksum
 assert o['plugin_count']==52 and o['lazy_config_loaded'] and o['lazyvim_loaded'] and o['mason_loaded'] and o['conform_loaded']
 assert o['stages']['mason_command']=={'ok':True,'value':True}
 assert o['stages']['mason_resolved_options']=={'ok':True,'value':{'ensure_installed':[]}}
 assert o['home_env_absent'] and o['host_home_absent'] and o['cap_eff_zero'] and o['input_readonly']
 assert len(o['route_table'].splitlines())==1 and not o['mason_packages_present']
 assert o['messages']=='' and o['errmsg']=='' and (work/'stderr.txt').read_bytes()==b''
 log=(work/'scratch/state/nvim/conform.log').read_text()
 for kind,(formatter,lines) in EXPECTED.items():
  x=o['fixtures'][kind]
  assert o['stages'][kind]=={'ok':True,'value':True}
  assert x['selected']==[{'available':True,'command':formatter,'name':formatter}]
  assert x['first']=={'callback':True,'error':'','did_edit':True,'lines':lines}
  assert x['second']=={'callback':True,'error':'','did_edit':False,'lines':lines}
  assert o['executable'][formatter]=={'available':1,'path':'/usr/bin/'+formatter}
  assert log.count(formatter+' exited with code 0')==2
 assert 'Run command: { "/usr/bin/shfmt", "-filename", "/work/fixture.sh", "-i", 2 }' in log
 assert 'Run command: { "/usr/bin/stylua", "--search-parent-directories", "--respect-ignores", "--stdin-filepath", "/work/fixture.lua", "-" }' in log
 before=(work/'host-binfmt-before.json').read_bytes();after=(work/'host-binfmt-after.json').read_bytes()
 assert before==after and r['host_binfmt_unchanged'] and hashlib.sha256(before).hexdigest()==r['host_binfmt_sha256']
 entries=json.loads(before);assert entries['status']=='enabled\n'
 assert 'interpreter /usr/bin/qemu-aarch64-static\n' in entries['qemu-aarch64'] and 'flags: PF\n' in entries['qemu-aarch64']
 mason=(work/'scratch/state/nvim/mason.log').read_text()
 assert 'Failed to update registries' in mason
 assert o['executable']['curl']=={'available':1,'path':'/usr/bin/curl'}
 assert r['curl_inputs'] and 'curl' in mason
 assert 'Spawning cmd="curl"' in mason and 'exit_code=6' in mason
 offline=o['stages']['curl_offline']
 assert offline['ok'] and offline['value']['code']==6 and 'Could not resolve host' in offline['value']['stderr']
 return {'schema':1,'status':'WORKS_SCOPED_FULL_LOADER_AND_STOCK_FORMATTING','full_Mason_registry':'BLOCKED_ISOLATED_NETWORK_REGISTRY_UNAVAILABLE','native_target_performance':'UNTESTED','hardware':'UNTESTED','production_patch':False,'host_binfmt_configuration_changed':False,'actual_conform_command_prefix':'none; preexisting kernel AArch64 binfmt handler used','native_interpreter_registration_fd_bytes':'UNTESTED; registry reports PF interpreter, current pathname hash pinned separately','all_expectations':'PASS'}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('work',type=Path);a=p.parse_args()
 print(json.dumps(check(a.work),indent=2,sort_keys=True))
if __name__=='__main__':
 if not __debug__:raise SystemExit('Optimized Python prohibited')
 main()
