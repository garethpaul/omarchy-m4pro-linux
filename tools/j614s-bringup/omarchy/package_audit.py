#!/usr/bin/env python3
"""Compare source package lists with an extracted pacman local database.

Reads only; absence means missing from this image, not absent from ARM repos.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile


def desc_fields(value):
    fields = {}
    key = None
    for line in value.splitlines():
        if line.startswith("%") and line.endswith("%"):
            key = line.strip("%")
            fields[key] = []
        elif line and key:
            fields[key].append(line)
    return fields


def package_names(path):
    return [name for line in path.read_text().splitlines()
            if (name := line.split("#", 1)[0].strip())]


def repository_records(path, diagnostics=None):
    """ALARM uses split desc/depends; newer repositories can inline both."""
    rows = {}
    with tarfile.open(path) as archive:
        for member in archive:
            if not member.isfile() or member.name.rsplit("/", 1)[-1] not in ("desc", "depends"):
                continue
            directory, _ = member.name.rsplit("/", 1)
            record = rows.setdefault(directory, {})
            fields = desc_fields(archive.extractfile(member).read().decode())
            for key, values in fields.items():
                if key in ("NAME", "VERSION", "ARCH") and key in record and record[key] != values:
                    raise ValueError("conflicting repository package identity")
                record[key] = list(dict.fromkeys(record.get(key, []) + values))
    for directory, row in rows.items():
        if not row.get("NAME"):
            if diagnostics is None:
                raise ValueError("repository package metadata lacks desc identity")
            diagnostics.append({"entry": directory, "reason": "missing desc identity; excluded from candidates"})
            continue
        yield row


def repository_index(repositories, *, include_payload=False):
    index = {}
    provenance = []
    candidates = []
    for repository, path in repositories:
        diagnostics = []
        provenance.append({"name": repository, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "excluded_metadata_entries": diagnostics})
        for fields in repository_records(path, diagnostics):
            arch = fields.get("ARCH", [""])[0]
            if arch not in ("aarch64", "any"):
                continue
            name = fields["NAME"][0]
            candidate = {"repository": repository, "name": name,
                         "version": fields["VERSION"][0], "architecture": arch}
            if include_payload:
                candidate.update(filename=fields.get("FILENAME", [None])[0],
                                 sha256=fields.get("SHA256SUM", [None])[0])
            # libalpm searches exact package names before choosing a provider.
            index.setdefault(name, candidate)
            candidates.append((candidate, fields.get("PROVIDES", [])))
    for candidate, provides in candidates:
        for alias in [entry.split("=", 1)[0] for entry in provides]:
            index.setdefault(alias, candidate)
    return index, provenance


def audit(database, lists, repositories=()):
    installed = {}
    providers = {}
    hashes = {}
    for path in sorted(database.glob("*/desc")):
        data = path.read_bytes()
        fields = desc_fields(data.decode())
        name = fields["NAME"][0]
        installed[name] = {"version": fields["VERSION"][0],
                           "architecture": fields["ARCH"][0]}
        hashes[name] = hashlib.sha256(data).hexdigest()
        for provided in fields.get("PROVIDES", []):
            providers.setdefault(provided.split("=", 1)[0], []).append(name)
    if not installed:
        raise ValueError("no pacman package descriptions found")
    repository_packages, provenance = repository_index(repositories)
    rows = []
    for path in lists:
        entries = []
        for name in dict.fromkeys(package_names(path)):
            candidates = [name] if name in installed else providers.get(name, [])
            candidates = [candidate for candidate in candidates
                          if installed[candidate]["architecture"] in ("aarch64", "any")]
            entries.append({"requested": name, "status": "installed" if candidates else "missing_from_image",
                            "installed_as": [{"name": candidate, **installed[candidate]}
                                             for candidate in candidates],
                            "repository_candidate": repository_packages.get(name)})
        rows.append({"list": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "requested_count": len(entries),
                     "missing_count": sum(row["status"] == "missing_from_image" for row in entries),
                     "packages": entries})
    return {"schema": 1, "scope": "immutable OS image local package database; not live target",
            "repository_availability": "metadata only; signatures and install transaction UNTESTED" if repositories
                                       else "UNTESTED; do not infer from image absence",
            "repositories": provenance,
            "dependency_transaction": "UNTESTED; installed names/provides only",
            "installed_count": len(installed),
            "local_descriptions_digest": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
            "lists": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--repository", action="append", default=[], metavar="NAME=DATABASE",
                        help="repository metadata in pacman order; never installed")
    parser.add_argument("lists", nargs="+", type=Path)
    args = parser.parse_args()
    repositories = [(name, Path(path)) for name, path in
                    (argument.split("=", 1) for argument in args.repository)]
    print(json.dumps(audit(args.database, args.lists, repositories), indent=2))


if __name__ == "__main__":
    main()
