#!/usr/bin/env python3
"""Read exact signed archive members as data and independently check GNU readelf."""
import argparse
import json
from pathlib import Path
import sys
import tarfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crosscheck_readelf import inspect
from audit_plan import safe_member, sha
from filesystem import verify_or_write

MEMBERS = {
    'opencv': 'usr/lib/libopencv_imgcodecs.so.5.0.0',
    'libtiff': 'usr/lib/libtiff.so.6.3.0',
    'openexr': 'usr/lib/libOpenEXRCore-3_5.so.34.3.5.2',
    'openjph': 'usr/lib/libopenjph.so.0.32.0',
    'jbigkit': 'usr/lib/libjbig.so.2.2',
    'unixodbc': 'usr/lib/libodbc.so.2.0.0',
    'freetds': 'usr/lib/libsybdb.so.5.1.0',
    'assimp': 'usr/lib/libassimp.so.6.0.5',
    'qt5-base': 'usr/lib/qt/plugins/sqldrivers/libqsqltds.so',
    'qt6-quick3d': 'usr/lib/qt6/plugins/assetimporters/libassimp.so',
}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('qualification', 'cache', 'restore', 'private', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    q = json.loads(a.qualification.read_text())
    packages = {r['name']: r for r in q['packages']}
    if not q['audit_complete'] or any(n not in packages for n in MEMBERS):
        raise ValueError('complete signed closure qualification required')
    a.private.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, member_name in MEMBERS.items():
        package = packages[name]
        archive_path = a.cache/'payloads'/package['sha256']/package['filename']
        if archive_path.stat().st_size != package['expected_bytes'] or sha(archive_path) != package['sha256']:
            raise ValueError('qualified archive bytes changed')
        with tarfile.open(archive_path) as archive:
            matches = [m for m in archive if safe_member(m.name) == member_name]
            if len(matches) != 1 or not matches[0].isfile() or matches[0].size > 128*1024*1024:
                raise ValueError('exact bounded regular archive member required')
            data = archive.extractfile(matches[0]).read()
        target = a.private/(name + '.elf')
        verify_or_write(target, data)
        row = inspect(target, member_name, a.private)
        row.update(package=name, version=package['version'], archive_sha256=package['sha256'])
        rows.append(row)
        if name in ('opencv', 'libtiff'):
            old = a.restore/member_name
            if not old.is_file() or old.is_symlink():
                raise ValueError('physical baseline regular file required')
            baseline = inspect(old, 'baseline/'+member_name, a.private)
            baseline.update(package=name, source='previously sealed immutable image; full model independently validates seal')
            rows.append(baseline)
    a.output.write_text(json.dumps({
        'status': 'WORKS: static independent readelf crosscheck only',
        'deployable': False, 'execution_ready': False, 'actions': [],
        'qualification_sha256': sha(a.qualification),
        'source_sha256': sha(Path(__file__)), 'rows': rows,
        'limits': ['No payload execution or runtime ABI test; GNU readelf reads bytes only.',
                   'The separate model binds every restored baseline file and all986 local descriptions.'],
    }, indent=2)+'\n')
    print('crosschecked', len(rows), 'actual AArch64 ELF files')

if __name__ == '__main__':
    main()
