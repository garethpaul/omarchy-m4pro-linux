#!/usr/bin/env python3
"""Exercise guarded mutations of the real pinned plan entirely in memory."""
import argparse
import copy
import json
from pathlib import Path
from audit_transaction import load_tools, pin_rows

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();records,protected=load_tools(a.source)
    original=json.loads((a.source/'evidence/pacman-print-resolution.json').read_text())
    provenance=json.loads((a.source/'evidence/repositories/provenance.json').read_text())
    rows=[]
    for name in ('control','protected selection','wrong architecture','wrong payload digest'):
        plan=copy.deepcopy(original)
        if name=='protected selection':
            item=copy.deepcopy(plan['resolved_transaction'][0]);item['name']='linux-aurora'
            plan['resolved_transaction'].append(item);plan['transaction_package_count']+=1
        elif name=='wrong architecture':plan['resolved_transaction'][0]['architecture']='x86_64'
        elif name=='wrong payload digest':plan['resolved_transaction'][0]['sha256']='0'*64
        failure=None
        try: count=len(pin_rows(plan,provenance,a.source,records,protected));accepted=True
        except ValueError as error: accepted=False;count=None;failure=str(error)
        if accepted!=(name=='control'):raise ValueError('real pinned plan guard failed')
        rows.append({'case':name,'accepted':accepted,'selected_count':count,'failure':failure,'network_or_install_actions':[]})
    a.output.write_text(json.dumps({'schema':1,'status':'WORKS','source_commit':'4941c67dbab65ec9bd903c337863c10a51741542','checks':rows},indent=2)+'\n')
if __name__=='__main__':main()
