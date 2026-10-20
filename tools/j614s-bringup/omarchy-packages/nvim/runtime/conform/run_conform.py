#!/usr/bin/env python3
"""Verified Conform plugin and native Neovim runtime; real-plugin formatting only inside bwrap."""
import argparse,hashlib,json,subprocess,shutil,tarfile,struct
from pathlib import Path

QEMU='66bdc286fd30970a1c3d2029b460605a3dc843ed6b397f4cd9825f9c19551507'
PROOF='000030a40d99f83c61afb0c94b665690ff68e1ad49879a541ef32fffe03f484f'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('root','proof','probe','work','output'):p.add_argument('--'+name,type=Path,required=True)
 for name in ('qualification','native-archive','seed-archive'):
  p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args()
 assert sha(a.qualification)=='30ce53399b1029787133348e2c0074d4ac85a76d3c867dc744a71f3b2b2ade2c'
 rows={r['name']:r for r in json.loads(a.qualification.read_text())['packages']}
 for name,archive in [('neovim',a.native_archive),('omarchy-nvim',a.seed_archive)]:
  assert sha(archive)==rows[name]['sha256']
  assert archive.stat().st_size==rows[name]['bytes']
  assert rows[name]['cryptographic_signature']=='WORKS'
  assert rows[name]['pkginfo_identity']=='WORKS'
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
 members=[]
 with tarfile.open(a.native_archive) as archive:
  for m in archive:
   if not m.name.startswith('usr/share/nvim/runtime/') or not m.isfile():continue
   rel=Path(m.name)
   assert '..' not in rel.parts and not rel.is_absolute()
   data=archive.extractfile(m).read()
   assert len(data)==m.size
   dest=owned/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);dest.chmod(m.mode&0o777)
   members.append({'archive':'neovim','member':m.name,'bytes':m.size,'mode':oct(m.mode),'sha256':hashlib.sha256(data).hexdigest()})
 prefix='etc/skel/.local/share/nvim/lazy/conform.nvim/'
 process=subprocess.Popen(['zstd','-dc',str(a.seed_archive)],stdout=subprocess.PIPE)
 plugin_commit=None
 with tarfile.open(fileobj=process.stdout,mode='r|') as archive:
  for m in archive:
   if not m.isfile() or not m.name.startswith(prefix):continue
   rel=m.name.removeprefix(prefix)
   if rel=='.git/refs/heads/master':plugin_commit=archive.extractfile(m).read().decode().strip()
   if rel=='.git/packed-refs':
    for line in archive.extractfile(m).read().decode().splitlines():
     if line.endswith(' refs/heads/master'):plugin_commit=line.split()[0]
   if not (rel.startswith('lua/') or rel in ('LICENSE','LICENSE.md')):continue
   path=Path(rel);assert '..' not in path.parts and not path.is_absolute()
   data=archive.extractfile(m).read();assert len(data)==m.size
   dest=owned/'conform'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);dest.chmod(m.mode&0o777)
   members.append({'archive':'omarchy-nvim','member':m.name,'bytes':m.size,'mode':oct(m.mode),'sha256':hashlib.sha256(data).hexdigest()})
 assert process.wait()==0
 assert (owned/'conform/lua/conform/init.lua').exists()
 assert (owned/'usr/share/nvim/runtime/lua/vim/_core/system.lua').exists()
 for item in members:
  if item['archive']=='neovim':dest=owned/item['member']
  else:dest=owned/'conform'/item['member'].removeprefix(prefix)
  assert sha(dest)==item['sha256']

 scratch=a.work/'scratch';scratch.mkdir();(scratch/'home').mkdir()
 cmd=['bwrap','--unshare-all','--uid','0','--gid','0','--cap-drop','ALL','--die-with-parent','--new-session',
      '--ro-bind',str(owned.resolve()),'/', '--ro-bind',str(a.probe.resolve()),'/probe.lua',
      '--bind',str(scratch.resolve()),'/work','--tmpfs','/tmp','--dev','/dev','--proc','/proc',
      '--chdir','/work','--clearenv','--setenv','PATH','/usr/bin','--setenv','LANG','C',
      '--setenv','XDG_CONFIG_HOME','/work/config','--setenv','XDG_DATA_HOME','/work/data',
      '--setenv','XDG_CACHE_HOME','/work/cache','--setenv','XDG_STATE_HOME','/work/state',
      '--setenv','NVIM_LOG_FILE','/work/nvim.log','--','/qemu','-L','/',
      '/usr/bin/nvim','--headless','-u','NONE','-i','NONE','-n','-l','/probe.lua']
 r=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
 a.output.mkdir(exist_ok=False)
 (a.output/'stderr.txt').write_text(r.stderr)
 (a.output/'result.json').write_text(json.dumps({'exit':r.returncode,'stdout':r.stdout,'stderr_file':'stderr.txt',
      'prior_root_proof_sha256':sha(a.proof),'probe_sha256':sha(a.probe),'runner_sha256':sha(Path(__file__)),
      'qualification_sha256':sha(a.qualification),'archive_sha256':{'neovim':sha(a.native_archive),'omarchy-nvim':sha(a.seed_archive)},'conform_git_commit':plugin_commit,'extracted_members':members,'unshare_all':True,'capabilities_dropped':True,'root_read_only':True,'host_HOME_exposed':False},indent=2)+'\n')
 if (scratch/'observations.json').exists():(a.output/'observations.json').write_bytes((scratch/'observations.json').read_bytes())
 if (scratch/'state/nvim/conform.log').exists():(a.output/'conform.log').write_bytes((scratch/'state/nvim/conform.log').read_bytes())
 assert r.returncode==0,r.stderr[-2000:]
if __name__=='__main__':main()
