#!/usr/bin/env python3
"""Create a new private read-only image-data restore; never mount or execute."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from audit_plan import IMAGE_SHA,IMAGE_SIZE,sha,restore_metadata
from filesystem import seal_tree

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--image',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('restore destination must not exist')
    if a.image.stat().st_size!=IMAGE_SIZE or sha(a.image)!=IMAGE_SHA:raise ValueError('retained image differs')
    trees=('usr/bin','usr/lib','usr/libexec','opt','etc/ld.so.conf.d','var/lib/pacman/local')
    prefixes={'/','/etc/ld.so.conf'}
    for value in trees:
        path=Path('/'+value);prefixes.update(str(p) for p in path.parents);prefixes.add(str(path)+'(/.*)?')
    regex='^('+'|'.join(sorted(re.escape(p[:-6])+'(/.*)?' if p.endswith('(/.*)?') else re.escape(p) for p in prefixes))+')$'
    a.output.mkdir(parents=True)
    command=['btrfs','restore','-S','-r256','--path-regex',regex,str(a.image),str(a.output)]
    subprocess.run(command,check=True,capture_output=True,text=True)
    seal_tree(a.output,{**restore_metadata(),'trees':list(trees),'file':'etc/ld.so.conf','method':'btrfs restore -S -r256 into new private destination; no mount or package execution'})
if __name__=='__main__':main()
