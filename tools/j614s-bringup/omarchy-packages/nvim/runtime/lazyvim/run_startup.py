#!/usr/bin/env python3
"""Reproduce packaged LazyVim startup inside the existing isolated ARM root."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import struct
import posixpath
import re

QUAL='30ce53399b1029787133348e2c0074d4ac85a76d3c867dc744a71f3b2b2ade2c'
PROOF='000030a40d99f83c61afb0c94b665690ff68e1ad49879a541ef32fffe03f484f'
QEMU='66bdc286fd30970a1c3d2029b460605a3dc843ed6b397f4cd9825f9c19551507'
OPTIONS='ee1c37fef7f501807d87b6700ffb6fc40da69982afd302f9b88333b78593feee'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def require(ok,message):
 if not ok:raise ValueError(message)

def put(root,name,data,mode,rows,origin):
 rel=PurePosixPath(name)
 require(not rel.is_absolute() and '..' not in rel.parts,'Unsafe archive member')
 target=root.joinpath(*rel.parts)
 require(not target.exists() and not target.is_symlink(),'Duplicate archive member')
 target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);target.chmod(mode&0o777)
 rows.append({'origin':origin,'member':name,'bytes':len(data),'mode':oct(mode),'sha256':sha(target)})

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('root','proof','qualification','native_archive','seed_archive','options','probe','work'):
  p.add_argument('--'+n.replace('_','-'),type=Path,required=True)
 p.add_argument('--git-archive',type=Path)
 p.add_argument('--baseline',type=Path)
 p.add_argument('--baseline-curl',action='store_true')
 a=p.parse_args();require(not a.work.exists(),'Fresh owned work directory required')
 require(sha(a.qualification)==QUAL and sha(a.proof)==PROOF,'Unreviewed provenance')
 proof=json.loads(a.proof.read_text());rows={x['name']:x for x in json.loads(a.qualification.read_text())['packages']}
 for name,path in [('neovim',a.native_archive),('omarchy-nvim',a.seed_archive)]:
  require(sha(path)==rows[name]['sha256'] and path.stat().st_size==rows[name]['bytes'],'Archive identity differs')
  require(rows[name]['cryptographic_signature']=='WORKS' and rows[name]['pkginfo_identity']=='WORKS','Unqualified archive')
 for x in proof['input_files']:require(sha(a.root/x['path'])==x['sha256'],'Baseline file differs')
 require(sha(a.root/'qemu')==QEMU and sha(a.options)==OPTIONS,'Dispatcher or options differs')
 a.work.mkdir(mode=0o700);owned=a.work/'root';owned.mkdir()
 # Copy only the proven executable/library files plus the dispatcher/passwd,
 # not arbitrary extras from an earlier writable runtime tree.
 for x in proof['input_files']:
  dest=owned/x['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a.root/x['path'],dest)
  dest.chmod(0o755 if x['path'].startswith('usr/bin/') else 0o644)
  require(sha(dest)==x['sha256'],'Copied proven input differs')
 (owned/'qemu').write_bytes((a.root/'qemu').read_bytes());(owned/'qemu').chmod(0o755)
 (owned/'usr/bin/qemu-aarch64-static').write_bytes((a.root/'qemu').read_bytes());(owned/'usr/bin/qemu-aarch64-static').chmod(0o755)
 (owned/'probe.lua').write_text('')
 (owned/'etc').mkdir();(owned/'etc/passwd').write_text('root:x:0:0:isolated:/work/home:/bin/false\n')
 (owned/'lib').symlink_to('usr/lib');(owned/'work').mkdir();(owned/'tmp').mkdir();(owned/'dev').mkdir();(owned/'proc').mkdir()
 members=[]
 git_inputs=[]
 require(bool(a.git_archive)==bool(a.baseline),'Git requires its explicit proven library baseline')
 if a.git_archive:
  row=rows['git']
  require(sha(a.git_archive)==row['sha256'] and a.git_archive.stat().st_size==row['bytes'],'Git archive differs')
  require(row['cryptographic_signature']=='WORKS' and row['pkginfo_identity']=='WORKS','Git archive unqualified')
  with tarfile.open(a.git_archive) as archive:
   data=archive.extractfile('usr/bin/git').read()
  require(data[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',data,18)[0]==183,'Expected ARM64 Git')
  put(owned,'usr/bin/git',data,0o755,git_inputs,'signed-git')
  manifest=a.baseline/'_abi-restore-manifest.json'
  require(sha(manifest)=='30a72f4608f94d7a4487e3529e7343bdf962a412d9c961b637a7bf196b54b947','Unqualified baseline manifest')
  baseline=json.loads(manifest.read_text());entries={r['path']:r for r in baseline['tree']['entries']}
  require(baseline['image_sha256']=='f6ceb11ef79914eaa10cc07637c929a99afe5982d216d8b89905c86e863b2491','Wrong baseline image')
  for library in ('libpcre2-8.so.0','libz-ng.so.2'):
   source=(a.baseline/'usr/lib'/library).resolve(strict=True);rel=source.relative_to(a.baseline.resolve())
   require(str(rel) in entries and sha(source)==entries[str(rel)]['sha256'],'Unqualified library')
   data=source.read_bytes();require(data[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',data,18)[0]==183,'Expected ARM64 library')
   put(owned,'usr/lib/'+library,data,0o644,git_inputs,'verified-baseline:'+str(rel))
  # Native parser dependencies declared by signed Neovim; keep the actual
  # packaged absolute aliases, interpreted only inside the private root.
  parser_links=[]
  for language in ('c','lua','markdown','markdown_inline','query','vim','vimdoc'):
   rel='usr/lib/tree_sitter/'+language+'.so';link=entries[rel]['link']
   require(link.startswith('/usr/lib/') and '..' not in PurePosixPath(link).parts,'Invalid baseline parser alias')
   actual=rel
   for _ in range(8):
    row=entries[actual]
    if 'sha256' in row:break
    target=row['link'];alias=owned/actual;alias.parent.mkdir(parents=True,exist_ok=True)
    require(not alias.exists() and not alias.is_symlink(),'Duplicate parser alias')
    alias.symlink_to(target);parser_links.append({'path':actual,'target':target})
    actual=target.removeprefix('/') if target.startswith('/') else posixpath.normpath(str(PurePosixPath(actual).parent/target))
    require(actual.startswith('usr/lib/') and '..' not in PurePosixPath(actual).parts,'Parser alias escaped library root')
   else:raise ValueError('Parser alias chain exceeds bound')
   source=a.baseline/actual
   require(not source.is_symlink() and sha(source)==entries[actual]['sha256'],'Parser baseline bytes differ')
   data=source.read_bytes();require(data[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',data,18)[0]==183,'Expected ARM64 parser')
   put(owned,actual,data,0o644,git_inputs,'verified-baseline:'+actual)
 curl_inputs=[]
 if a.baseline_curl:
  require(a.baseline is not None,'Sealed baseline required for Curl')
  queue=['usr/bin/curl'];seen=set()
  while queue:
   require(len(seen)<128,'Curl closure exceeds bound')
   requested=queue.pop(0)
   if requested in seen:continue
   seen.add(requested);actual=requested
   for _ in range(16):
    row=entries[actual]
    if 'sha256' in row:break
    target=row['link'];alias=owned/actual;alias.parent.mkdir(parents=True,exist_ok=True)
    if alias.is_symlink():require(alias.readlink().as_posix()==target,'Existing Curl alias differs')
    else:
     require(not alias.exists(),'Unexpected existing Curl alias path');alias.symlink_to(target)
    curl_inputs.append({'origin':'verified-baseline','member':actual,'symlink':target})
    actual=target.removeprefix('/') if target.startswith('/') else posixpath.normpath(str(PurePosixPath(actual).parent/target))
    require(actual.startswith(('usr/lib/','usr/bin/')) and '..' not in PurePosixPath(actual).parts,'Curl alias escaped allowed root')
   else:raise ValueError('Curl alias chain exceeds bound')
   source=a.baseline/actual;require(not source.is_symlink() and sha(source)==entries[actual]['sha256'],'Curl member differs')
   data=source.read_bytes();require(data[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',data,18)[0]==183,'Expected ARM64 Curl closure')
   dest=owned/actual
   if dest.exists():
    require(not dest.is_symlink() and sha(dest)==sha(source),'Existing library differs from Curl baseline')
    curl_inputs.append({'origin':'verified-baseline-reused','member':actual,'bytes':len(data),'sha256':sha(dest)})
   else:put(owned,actual,data,0o755 if actual.startswith('usr/bin/') else 0o644,curl_inputs,'verified-baseline:'+actual)
   dynamic=subprocess.run(['readelf','--dynamic','--wide',str(source)],capture_output=True,text=True,check=True)
   for needed in re.findall(r'\(NEEDED\).*Shared library: \[([^\]]+)\]',dynamic.stdout):
    require(re.fullmatch(r'[A-Za-z0-9_.+-]+',needed) is not None,'Unsafe library dependency')
    queue.append('usr/lib/'+needed)
 for name in ('shfmt','stylua'):
  data=(owned/'usr/bin'/name).read_bytes()
  require(data[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',data,18)[0]==183,'Expected ARM64 formatter')
 host_interpreter=Path('/usr/bin/qemu-aarch64-static')
 require(sha(host_interpreter)==QEMU,'Current host interpreter pathname differs')
 binfmt={n:Path('/proc/sys/fs/binfmt_misc',n).read_text() for n in ('status','qemu-aarch64')}
 (a.work/'host-binfmt-before.json').write_text(json.dumps(binfmt,indent=2,sort_keys=True)+'\n')
 with tarfile.open(a.native_archive) as archive:
  for m in archive:
   if m.isfile() and m.name.startswith('usr/share/nvim/runtime/'):
    put(owned,m.name,archive.extractfile(m).read(),m.mode,members,'signed-neovim')
 if a.baseline:
  # This symlink is an exact member of the hash-qualified native archive.
  with tarfile.open(a.native_archive) as archive:
   parser=archive.getmember('usr/share/nvim/runtime/parser')
   require(parser.issym() and parser.linkname=='/usr/lib/tree_sitter','Unexpected runtime parser alias')
  (owned/'usr/share/nvim/runtime/parser').symlink_to(parser.linkname)
 scratch=a.work/'scratch';scratch.mkdir();(scratch/'home').mkdir()
 excluded=[]
 stream=subprocess.Popen(['zstd','-dc',str(a.seed_archive)],stdout=subprocess.PIPE)
 with tarfile.open(fileobj=stream.stdout,mode='r|') as archive:
  for m in archive:
   prefixes={'etc/skel/.config/nvim/':'config/nvim/','etc/skel/.local/share/nvim/lazy/':'data/nvim/lazy/'}
   for prefix,dest in prefixes.items():
    if not m.name.startswith(prefix):continue
    rel=m.name.removeprefix(prefix)
    if m.isfile():put(scratch,dest+rel,archive.extractfile(m).read(),m.mode,members,'signed-omarchy-nvim')
    elif m.issym():excluded.append({'member':m.name,'kind':'symlink','target':m.linkname})
 require(stream.wait()==0,'Archive decompression failed')
 # Model only the already reviewed source candidate's native-formatters overlay.
 dest=scratch/'config/nvim/lua/plugins/native-formatters.lua';require(not dest.exists(),'Unexpected overlay collision')
 dest.write_bytes(a.options.read_bytes());dest.chmod(0o644)
 required=scratch/'config/nvim/init.lua';require(required.is_file(),'Missing packaged startup')
 manifest=a.work/'members.jsonl';manifest.write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in members))
 cmd=['bwrap','--unshare-all','--uid','0','--gid','0','--cap-drop','ALL','--die-with-parent','--new-session','--ro-bind',str(owned.resolve()),'/',
 '--ro-bind',str(a.probe.resolve()),'/probe.lua','--bind',str(scratch.resolve()),'/work','--tmpfs','/tmp','--dev','/dev','--proc','/proc','--chdir','/work','--clearenv',
 '--setenv','PATH','/usr/bin','--setenv','LANG','C','--setenv','XDG_CONFIG_HOME','/work/config','--setenv','XDG_DATA_HOME','/work/data','--setenv','XDG_STATE_HOME','/work/state','--setenv','XDG_CACHE_HOME','/work/cache','--setenv','GIT_CONFIG_COUNT','4','--setenv','GIT_CONFIG_KEY_0','core.hooksPath','--setenv','GIT_CONFIG_VALUE_0','/nonexistent-hooks','--setenv','GIT_CONFIG_KEY_1','core.fsmonitor','--setenv','GIT_CONFIG_VALUE_1','false','--setenv','GIT_CONFIG_KEY_2','gc.auto','--setenv','GIT_CONFIG_VALUE_2','0','--setenv','GIT_CONFIG_KEY_3','maintenance.auto','--setenv','GIT_CONFIG_VALUE_3','false','--setenv','NVIM_LOG_FILE','/work/nvim.log',
 '--','/qemu','-L','/','/usr/bin/nvim','--headless','-u','/work/config/nvim/init.lua','-i','NONE','-n','-c',"lua vim.api.nvim_create_autocmd('VimEnter', {once=true, callback=function() vim.defer_fn(function() dofile('/probe.lua') end, 100) end})"]
 try:
  result=subprocess.run(cmd,capture_output=True,timeout=30);code=result.returncode;stdout=result.stdout;stderr=result.stderr;timed_out=False
 except subprocess.TimeoutExpired as e:
  code=None;stdout=e.stdout or b'';stderr=e.stderr or b'';timed_out=True
 after={n:Path('/proc/sys/fs/binfmt_misc',n).read_text() for n in ('status','qemu-aarch64')}
 (a.work/'host-binfmt-after.json').write_text(json.dumps(after,indent=2,sort_keys=True)+'\n')
 require(after==binfmt and sha(host_interpreter)==QEMU,'Host binfmt state or interpreter pathname changed during test')
 (a.work/'stdout.txt').write_bytes(stdout);(a.work/'stderr.txt').write_bytes(stderr)
 record={'schema':1,'status':'OBSERVATION_ONLY','exit':code,'timed_out':timed_out,'qualification_sha256':QUAL,'proof_sha256':PROOF,'qemu_sha256':QEMU,'options_sha256':OPTIONS,'runner_sha256':sha(Path(__file__)),'probe_sha256':sha(a.probe),'members_manifest_sha256':sha(manifest),'members':len(members),'git_inputs':git_inputs,'curl_inputs':curl_inputs,'parser_links':parser_links if a.baseline else [],'host_binfmt_sha256':sha(a.work/'host-binfmt-before.json'),'host_binfmt_unchanged':True,'host_interpreter_path_sha256':sha(host_interpreter),'formatter_ELF_machine':183,'formatter_files':{n:sha(owned/'usr/bin'/n) for n in ('shfmt','stylua')},'excluded_symlinks':excluded,'omitted_mason_cache':'Matches reviewed source candidate; no Mason binary or receipt extracted','runtime_root_read_only':True,'host_home_exposed':False,'network_unshared':True,'capabilities_dropped':True,'target_access':False,'package_installation':False,'frozen151_modified':False,'hardware':'UNTESTED'}
 (a.work/'result.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'exit':code,'timed_out':timed_out,'members':len(members),'stdout_bytes':len(stdout),'stderr_bytes':len(stderr)}))

if __name__=='__main__':main()
