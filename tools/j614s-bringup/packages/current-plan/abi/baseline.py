"""Bind all local package descriptions to the fixed qualified image baseline."""
import hashlib
import json
from pathlib import Path

QUALIFICATION_SHA='d63559fc4cad4c7e3974cbc71acaee9ddfc9d1b4b6d67b6eff13e44a17d16eb7'
DESCRIPTION_DIGEST='05592373e5f03cfcfeb32ea3dcf0fb835b307e9e1eae75540e670db36e5e1e7e'
DESCRIPTION_COUNT=986
IMAGE_SHA='f6ceb11ef79914eaa10cc07637c929a99afe5982d216d8b89905c86e863b2491'

def description_identity(root):
    rows={}
    for path in sorted(root.glob('*/desc')):
        if path.is_symlink()or not path.is_file()or path.stat().st_size>2*1024*1024:raise ValueError('requires bounded regular description files')
        rows[path.parent.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    # Preserve the exact original qualification's default JSON spacing/key sort.
    return {'count':len(rows),'digest':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()}

def assert_identity(root,expected):
    actual=description_identity(root)
    if actual!=expected:raise ValueError('complete baseline description identity differs')
    return actual

def qualification(path):
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=QUALIFICATION_SHA:raise ValueError('fixed original baseline qualification changed')
    value=json.loads(data)
    if value['installed_image_local_description_digest']!=DESCRIPTION_DIGEST or value['installed_image_local_description_count']!=DESCRIPTION_COUNT or value['image_manifest']['image_sha256']!=IMAGE_SHA:raise ValueError('fixed qualified baseline identity differs')
    return {'count':DESCRIPTION_COUNT,'digest':DESCRIPTION_DIGEST}

def verify(root,path):return assert_identity(root,qualification(path))

def default_qualification():return Path(__file__).resolve().parents[2]/'evidence/transaction-audit.json'
