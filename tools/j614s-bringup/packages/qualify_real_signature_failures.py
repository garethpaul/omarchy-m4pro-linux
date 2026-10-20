#!/usr/bin/env python3
"""Negative checks using a real verified payload/signature, never executing payloads."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from audit_transaction import signature_result, key_material

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();proof=json.loads(a.audit.read_text())
    selected=next(r for r in proof['packages'] if r['status']=='WORKS')
    original=a.cache/'payloads'/selected['sha256']/selected['filename'];sig=original.with_name(original.name+'.sig')
    keys=key_material(a.source/'evidence/package-root/usr/share/pacman/keyrings',a.cache)
    rows=[]
    with tempfile.TemporaryDirectory(dir=a.cache) as folder:
        root=Path(folder);bad=root/'mutated-payload';shutil.copyfile(original,bad)
        with bad.open('r+b') as stream:
            value=stream.read(1);stream.seek(0);stream.write(bytes([value[0]^1]))
        empty=root/'empty.gpg';empty.write_bytes(b'')
        for name,payload,rings in [('control',original,keys['rings']),('mutated payload',bad,keys['rings']),('missing public key',original,[str(empty)])]:
            command=['gpgv','--homedir',str(a.cache/'gnupg'),'--status-fd','1']
            for ring in rings:command+=['--keyring',ring]
            result=subprocess.run(command+[str(sig),str(payload)],capture_output=True,text=True)
            accepted=True;failure=None
            try: signature_result(result.returncode,result.stdout,keys)
            except ValueError as error:accepted=False;failure=str(error)
            if accepted!=(name=='control'):raise ValueError('real signature negative/control failed')
            rows.append({'case':name,'exit':result.returncode,'accepted':accepted,'failure':failure,'gpg_status':result.stdout.splitlines()})
    a.output.write_text(json.dumps({'schema':1,'package':selected['name'],'payload_sha256':selected['sha256'],'checks':rows,'status':'WORKS'},indent=2)+'\n')
if __name__=='__main__':main()
