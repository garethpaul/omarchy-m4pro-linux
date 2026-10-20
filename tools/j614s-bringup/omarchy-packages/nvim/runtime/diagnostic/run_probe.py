#!/usr/bin/env python3
"""Read-only prior verified root, isolated diagnostic only; no payload outside bwrap."""
import argparse,hashlib,json,subprocess,shutil
from pathlib import Path

QEMU='66bdc286fd30970a1c3d2029b460605a3dc843ed6b397f4cd9825f9c19551507'
PROOF='000030a40d99f83c61afb0c94b665690ff68e1ad49879a541ef32fffe03f484f'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('root','proof','probe','work','output'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--strace',action='store_true')
 a=p.parse_args()
 assert sha(a.proof)==PROOF
 d=json.loads(a.proof.read_text());assert d['status'].startswith('WORKS')
 for row in d['input_files']:assert sha(a.root/row['path'])==row['sha256']
 assert sha(a.root/'qemu')==QEMU==d['emulator_sha256']
 assert sha(a.root/'native-formatters.lua')==d['options_sha256']
 a.work.mkdir(exist_ok=False)
 owned=a.work/'input-root';shutil.copytree(a.root,owned,symlinks=True)
 shutil.copyfile(owned/'qemu',owned/'usr/bin/qemu-aarch64-static')
 (owned/'usr/bin/qemu-aarch64-static').chmod(0o755)
 assert sha(owned/'usr/bin/qemu-aarch64-static')==QEMU
 scratch=a.work/'scratch';scratch.mkdir();(scratch/'home').mkdir()
 cmd=['bwrap','--unshare-all','--uid','0','--gid','0','--cap-drop','ALL','--die-with-parent','--new-session',
      '--ro-bind',str(owned.resolve()),'/', '--ro-bind',str(a.probe.resolve()),'/probe.lua',
      '--bind',str(scratch.resolve()),'/work','--tmpfs','/tmp','--dev','/dev','--proc','/proc',
      '--chdir','/work','--clearenv','--setenv','PATH','/usr/bin','--setenv','LANG','C',
      '--setenv','XDG_CONFIG_HOME','/work/config','--setenv','XDG_DATA_HOME','/work/data',
      '--setenv','XDG_CACHE_HOME','/work/cache','--setenv','XDG_STATE_HOME','/work/state',
      '--setenv','NVIM_LOG_FILE','/work/nvim.log','--','/qemu',*(['-strace'] if a.strace else []),'-L','/',
      '/usr/bin/nvim','--headless','-u','NONE','-i','NONE','-n','-l','/probe.lua']
 r=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
 a.output.mkdir(exist_ok=False)
 (a.output/'guest-strace.txt').write_text(r.stderr)
 (a.output/'result.json').write_text(json.dumps({'exit':r.returncode,'stdout':r.stdout,'stderr_file':'guest-strace.txt',
      'prior_root_proof_sha256':sha(a.proof),'probe_sha256':sha(a.probe),'runner_sha256':sha(Path(__file__)),
      'guest_strace_enabled':a.strace,'unshare_all':True,'capabilities_dropped':True,'root_read_only':True,'host_HOME_exposed':False},indent=2)+'\n')
 if (scratch/'observations.json').exists():(a.output/'observations.json').write_bytes((scratch/'observations.json').read_bytes())
 assert r.returncode==0,r.stderr[-2000:]
if __name__=='__main__':main()
