#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cross-check the strict parser against m1n1, emitting no ADT payloads."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from layout import parse_adt, require

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--proxyclient', type=Path, required=True)
parser.add_argument('--adt', type=Path, action='append', required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.proxyclient.resolve()))
from m1n1.adt import ADTNodeStruct
rows = []
for path in args.adt:
    raw = path.read_bytes()
    reference = {}
    def visit(node, parent=''):
        props = {p.name: p.value for p in node.properties}
        full = parent + '/' + props['name'].rstrip(b'\0').decode('ascii')
        key = full.removeprefix('/device-tree') or '/'
        candidate, index = key, 1
        while candidate in reference:
            index += 1
            candidate = f'{key}#{index}'
        reference[candidate] = props
        for child in node.children:
            visit(child, full)
    visit(ADTNodeStruct.parse(raw))
    own = parse_adt(raw)
    require(own == reference, 'strict parser differs from m1n1 reference')
    rows.append({'source_sha256': hashlib.sha256(raw).hexdigest(), 'node_count': len(own),
                 'status': 'WORKS for offline parser equivalence', 'raw_payload_exported': False})
args.output.write_text(json.dumps({'schema': 1, 'hardware_execution': 'UNTESTED', 'parsers': rows}, indent=2) + '\n')
