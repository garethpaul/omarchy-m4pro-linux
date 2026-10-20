#!/usr/bin/env python3
"""Share identical archive member provenance; preserve all execution result fields."""
import argparse,hashlib,json
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('raw-result','members','result'):p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args()
 raw=a.raw_result.read_bytes();d=json.loads(raw);members=d.pop('extracted_members')
 content=''.join(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n' for row in members).encode()
 if a.members.exists():assert a.members.read_bytes()==content
 else:a.members.write_bytes(content)
 d['extracted_members_manifest']={'file':'../'+a.members.name,'sha256':hashlib.sha256(content).hexdigest(),'count':len(members)}
 d['curation']={'raw_result_sha256':hashlib.sha256(raw).hexdigest(),'operation':'move unchanged extracted_members rows to shared JSONL; preserve all execution fields'}
 a.result.write_text(json.dumps(d,indent=2)+'\n')
if __name__=='__main__':main()
