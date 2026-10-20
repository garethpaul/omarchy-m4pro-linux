#!/usr/bin/env python3
"""Read-only USB DT and exact source comparison; no target API or raw ADT."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

NODES=['/interrupt-controller@502400000','/phy@38aa90000','/iommu@38af00000','/iommu@38af80000','/usb@38a280000']
FILES=['drivers/usb/dwc3/core.c','drivers/usb/dwc3/gadget.c','drivers/usb/dwc3/ep0.c','drivers/usb/gadget/function/f_acm.c','drivers/usb/gadget/function/u_serial.c','drivers/usb/gadget/configfs.c','drivers/phy/apple/usb2-t6040-inherited.c','drivers/iommu/apple-dart.c']

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def props(path):
    rows={};ids={}
    for node in NODES:
        rows[node]={}
        for prop in subprocess.check_output(['fdtget','-p',str(path),node],text=True).splitlines():
            text=subprocess.check_output(['fdtget','-t','bx',str(path),node,prop],text=True).split()
            value=bytes(int(v,16) for v in text);rows[node][prop]=value
            if prop=='phandle':ids[struct.unpack('>I',value)[0]]=node
    for node in rows:
        for prop in ('phandle','interrupt-parent','phys','iommus'):
            if prop not in rows[node]:continue
            data=rows[node][prop];words=struct.unpack('>'+str(len(data)//4)+'I',data)
            if prop=='phandle':rows[node][prop]=node
            elif prop=='iommus':rows[node][prop]=[(ids[words[i]],words[i+1]) for i in range(0,len(words),2)]
            else:rows[node][prop]=[ids[v] for v in words]
        rows[node]={k:v.hex() if type(v) is bytes else v for k,v in rows[node].items()}
    return rows


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--old',type=Path,required=True);p.add_argument('--new',type=Path,required=True);p.add_argument('--old-dtb',type=Path,required=True);p.add_argument('--new-dtb',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    old,new=props(a.old_dtb),props(a.new_dtb)
    if old!=new:raise ValueError('USB/AIC DT properties differ')
    sources={f:dict(old_sha256=sha(a.old/f),new_sha256=sha(a.new/f),identical=sha(a.old/f)==sha(a.new/f)) for f in FILES}
    configold=(a.old_dtb.parent/'kernel.config').read_text().splitlines();confignew=(a.new/'../overnight-infra-gravity-combined-build-03/build/.config').read_text().splitlines()
    select=lambda lines:{l.split('=')[0]:l for l in lines if l.startswith('CONFIG_') and any(k in l.split('=')[0] for k in ('USB','IOMMU','DMA','ARM_LPAE','ARM_V7S','PREEMPT'))}
    x,y=select(configold),select(confignew);delta={k:{'old':x.get(k),'new':y.get(k)} for k in sorted(x.keys()|y.keys()) if x.get(k)!=y.get(k)}
    result=dict(schema=1,status='USB_DT_SEMANTIC_MATCH',hardware='UNTESTED',old_dtb_sha256=sha(a.old_dtb),new_dtb_sha256=sha(a.new_dtb),nodes=old,source_files=sources,filtered_config_differences=delta,scope='Static USB1/PHY/DART/AIC properties only; phandle IDs normalized; no runtime capture addresses emitted')
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print('PASS exact USB1/PHY/DART/AIC properties after phandle normalization')
