#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Derive a publishable display-only fact set from private offline evidence.

Never emits raw ADT properties, firmware bytes, symbol tables or assembly.
"""
import argparse, hashlib, json, re
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--comparison',type=Path,required=True)
p.add_argument('--firmware-root',type=Path,required=True)
p.add_argument('--output',type=Path,required=True);a=p.parse_args()
raw=a.comparison.read_bytes();comparison=json.loads(raw)
paths=['/arm-io/disp0','/arm-io/dcp','/arm-io/dart-dcp','/arm-io/dart-disp0']
# Explicit property allowlist excludes every other ADT property.
allowed=['compatible','registers','interrupts','clock-gates','power-gates']
nodes={path:{variant:{key:value for key,value in fields.items() if key in allowed}
       for variant,fields in comparison['nodes'][path].items()} for path in paths}
firmware={}
for model in ['j614sap','j613ap','j413ap','j700ap']:
 b=(a.firmware_root/model/'DCP.payload').read_bytes()
 builds=sorted({m.group().decode() for m in re.finditer(rb'AppleDCP-[0-9.]+~[0-9]+-[a-z0-9]+\.RELEASE',b)})
 rtkit=sorted({m.group().decode() for m in re.finditer(rb'RTKit-[0-9.]+\.release',b)})
 if len(builds)!=1 or len(rtkit)!=1:raise SystemExit('firmware identity ambiguous for '+model)
 firmware[model]={'payload_sha256':hashlib.sha256(b).hexdigest(),'size':len(b),'build':builds[0],'rtkit':rtkit[0]}
result={'scope':'Offline measured ADT facts and firmware build identity only; shared release is not ABI qualification',
        'comparison_sha256':hashlib.sha256(raw).hexdigest(),'hardware_tested_by_this_tool':False,
        'nodes':nodes,'firmware_25G83':firmware}
a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'status':'DERIVED_FACTS_ONLY','nodes':paths,'firmware':firmware},indent=2))
