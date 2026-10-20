"""Data-only cache integrity and sealed read-only restore identities."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat

MANIFEST='_abi-restore-manifest.json'

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
    return h.hexdigest()

def canonical(data):return json.dumps(data,sort_keys=True,separators=(',',':')).encode()

def tree_identity(root):
    entries=[]
    def walk(folder):
        for entry in sorted(os.scandir(folder),key=lambda e:e.name):
            path=Path(entry.path);rel=path.relative_to(root).as_posix()
            if rel==MANIFEST:continue
            info=entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):entries.append({'path':rel,'link':os.readlink(path)})
            elif stat.S_ISDIR(info.st_mode):entries.append({'path':rel,'directory':True});walk(path)
            elif stat.S_ISREG(info.st_mode):
                fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
                with os.fdopen(fd,'rb') as f:
                    before=os.fstat(f.fileno());h=hashlib.sha256()
                    for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
                    after=os.fstat(f.fileno())
                identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
                if identity(before)!=identity(after) or identity(info)!=identity(before):raise ValueError('restore file changed during identity read')
                entries.append({'path':rel,'sha256':h.hexdigest(),'bytes':info.st_size})
            else:raise ValueError('unsupported special file in restore')
    walk(root)
    return {'entries':entries,'entry_count':len(entries),'entries_sha256':hashlib.sha256(canonical(entries)).hexdigest()}

def seal_tree(root,metadata):
    path=root/MANIFEST
    if path.exists() or path.is_symlink():raise ValueError('restore already sealed')
    value={**metadata,'tree':tree_identity(root)}
    path.write_bytes(canonical(value)+b'\n')
    return value

def validate_tree(root,expected_metadata):
    path=root/MANIFEST
    if path.is_symlink() or not path.is_file():raise ValueError('fresh extractor-sealed restore required')
    value=json.loads(path.read_bytes())
    if {k:value.get(k) for k in expected_metadata}!=expected_metadata:raise ValueError('restore extraction provenance differs')
    if tree_identity(root)!=value.get('tree'):raise ValueError('restore file/link identities changed after extraction')
    return value,sha(path)

def write_cache(path,payload):
    if path.exists():raise ValueError('immutable cache destination exists')
    with path.open('xb') as f:
        with gzip.GzipFile(fileobj=f,mode='wb',mtime=0,compresslevel=3) as out:out.write(canonical(payload))
    path.with_name(path.name+'.sha256').write_text(sha(path)+'\n')

def read_cache(path):
    guard=path.with_name(path.name+'.sha256')
    if path.is_symlink() or guard.is_symlink() or not guard.is_file() or guard.read_text().strip()!=sha(path):raise ValueError('cache integrity changed')
    with gzip.open(path,'rb') as f:return json.load(f)

def cache_path(private,prefix,key):return private/(prefix+'-'+hashlib.sha256(canonical(key)).hexdigest()+'.json.gz')

def verify_or_write(path,data):
    expected=hashlib.sha256(data).hexdigest()
    if path.is_symlink():raise ValueError('reused provider bytes differ: symlink')
    if path.exists():
        if not path.is_file() or sha(path)!=expected:raise ValueError('reused provider bytes differ from exact archive member')
    else:
        with path.open('xb') as out:out.write(data)
    if sha(path)!=expected:raise ValueError('provider bytes differ after materialization')
