#!/usr/bin/env python3
"""Verify retained image and extract hook/keyring/Exec data without mounting or executing it."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
from audit_transaction import sha, baseline_hooks
IMAGE_SHA='f6ceb11ef79914eaa10cc07637c929a99afe5982d216d8b89905c86e863b2491'
IMAGE_SIZE=14344519680

def restore(image, output, patterns):
    prefixes={'/'}
    for value,recursive in patterns:
        path=Path('/'+value)
        prefixes.update(str(p) for p in path.parents)
        prefixes.add(str(path)+('(/.*)?' if recursive else ''))
    # Escape literal file names, retaining only our own subtree suffix.
    expressions=[re.escape(p[:-6])+'(/.*)?' if p.endswith('(/.*)?') else re.escape(p) for p in prefixes]
    pattern='^('+'|'.join(sorted(expressions))+')$'
    output.mkdir(parents=True,exist_ok=True)
    command=['btrfs','restore','-S','-o','-r256','--path-regex',pattern,str(image),str(output)]
    result=subprocess.run(command,capture_output=True,text=True)
    if result.returncode: raise ValueError('read-only btrfs restore failed: '+result.stderr)

def inventory(output):
    entries={}
    for path in sorted(output.rglob('*')):
        if path == output/'manifest.json': continue
        if path.is_file() and not path.is_symlink(): entries[path.relative_to(output).as_posix()]={'sha256':sha(path),'bytes':path.stat().st_size}
        elif path.is_symlink(): entries[path.relative_to(output).as_posix()]={'symlink':os.readlink(path)}
    return entries

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--image',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists(): raise ValueError('snapshot output must be a new disposable directory')
    if a.image.stat().st_size!=IMAGE_SIZE or sha(a.image)!=IMAGE_SHA: raise ValueError('retained image identity mismatch')
    restore(a.image,a.output,[(x,True) for x in ('usr/share/libalpm/hooks','etc/pacman.d/hooks','usr/share/pacman/keyrings')])
    baseline=baseline_hooks(a.output); commands=[]
    for row in baseline['effective']:
        for section in row.get('sections',[]):
            commands+=section['fields'].get('Exec',[])
    # First argv only, no shell expansion, no inferred helper execution.
    programs=sorted({shlex.split(c)[0].lstrip('/') for c in commands})
    # /bin is an image symlink; inspect canonical /usr/bin text rather than traverse links.
    programs=sorted({('usr/'+x if x.startswith('bin/') else x) for x in programs})
    restore(a.image,a.output,[(x,False) for x in programs])
    entries=inventory(a.output)
    (a.output/'manifest.json').write_text(json.dumps({'image_sha256':IMAGE_SHA,'image_bytes':IMAGE_SIZE,'root':256,'method':'read-only btrfs restore; no mount or payload execution','entries':entries,'exec_first_argv':programs},indent=2)+'\n')
if __name__=='__main__':main()
