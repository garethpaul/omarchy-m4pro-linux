#!/usr/bin/env python3
"""Offline ADT inventory: owner/property names and source-intended attribute classes.

No physical addresses, property values, firmware contents or raw ADT are emitted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--workspace', type=Path, required=True)
p.add_argument('--artifact', default='hardware-private/j614s-live-graphics-adt.bin')
a = p.parse_args()
w = a.workspace.resolve()
sys.path.insert(0, str(w/'m1n1-native/proxyclient'))
from m1n1.adt import ADTNodeStruct
path = w/a.artifact
raw = path.read_bytes()
root = ADTNodeStruct.parse(raw)
nodes = {}
def walk(node, parent=None):
    props = {x.name: bytes(x.value) for x in node.properties}
    name = props.get('name', b'').split(b'\0')[0].decode('ascii', 'replace')
    node_path = '/' if parent is None else parent.rstrip('/')+'/'+name
    nodes[node_path] = props
    for child in node.children:
        walk(child, node_path)
walk(root)
selected = ['/arm-io/ans', '/arm-io/ans/iop-ans-nub', '/arm-io/sart-ans', '/chosen/memory-map', '/defaults']
assert all(n in nodes for n in selected), 'expected owner/property namespace absent'
allowed = {
    '/arm-io/ans': {'reg','iommu-parent','AAPL,phandle','interrupts','nvme-secure-bar','nvme-linear-sq','nvme-queue-entries'},
    '/arm-io/ans/iop-ans-nub': {'region-base','region-size','segment-names','segment-ranges','running','pre-loaded','quiesced','shutdown-sleep','power-managed','AAPL,phandle'},
    '/arm-io/sart-ans': {'reg','AAPL,phandle','compatible','locked','protected-regions'},
    '/chosen/memory-map': {'RTBuddySeg'}, '/defaults': {'pmap-io-ranges'},
}
rows = [{'node': n, 'properties': [{'name': key, 'encoded_bytes': len(value)} for key,value in nodes[n].items() if key in allowed[n]]} for n in selected]
ans = nodes['/arm-io/ans'];sart = nodes['/arm-io/sart-ans'];nub = nodes['/arm-io/ans/iop-ans-nub']
owner_match = ans.get('iommu-parent') == sart.get('AAPL,phandle') and len(ans.get('iommu-parent',b'')) == 4
ranges = nodes['/defaults']['pmap-io-ranges'];assert len(ranges)%24==0
pmap = [struct.unpack_from('<QQII', ranges, offset) for offset in range(0,len(ranges),24)]
segments = nub['segment-ranges'];assert len(segments)%32==0
rtbuddy = nodes['/chosen/memory-map']['RTBuddySeg'];assert len(rtbuddy)==16
rt_base,rt_size = struct.unpack('<QQ',rtbuddy)
classes = []
for index,offset in enumerate(range(0,len(segments),32)):
    phys,iova,remap,size,unknown = struct.unpack_from('<QQQII',segments,offset)
    matches = []
    for base,length,flags,label in pmap:
        if size and phys>=base and phys-base<=length and size<=length-(phys-base):
            matches.append('Normal-NC' if flags==0x60004016 else 'Device-nGnRE' if flags>>28==8 else 'not classified by current pmap mapper')
    classes.append({'ordinal': index, 'source_intended_identity_override_classes': sorted(set(matches)),
                    'inside_rtbuddy_envelope': bool(size and phys>=rt_base and phys-rt_base<=rt_size and size<=rt_size-(phys-rt_base)),
                    'actual_shared_buffer_or_cache_ownership_proven': False})
report = {'status':'PARTIAL (offline property provenance only)', 'artifact': a.artifact,
          'artifact_sha256':hashlib.sha256(raw).hexdigest(),'values_or_addresses_exported':False,
          'target_access':False,'nodes':rows,'ans_iommu_parent_resolves_to_sart_ans':owner_match,
          'nub_segment_record_bytes':32,'nub_segment_count':len(classes),'segment_attribute_inferences':classes,
          'limits':['nub region/segments identify firmware allocations, not per-endpoint RTKit host buffers',
                    'RTBuddySeg is an allocation envelope, not a cache or ownership certificate',
                    'pmap overlap classes describe this captured input under current source, not active page-table or EL2 proof',
                    'properties running/pre-loaded/quiesced are cached descriptors, not a current live state check']}
print(json.dumps(report,indent=2))
