#!/usr/bin/env python3
"""Resolve the non-protected review requests using pacman's print-only mode.

No database refresh, downloads, install, hooks, full upgrade or target access.
All database/root/cache/log files belong to a new disposable review directory.
The full source request plan stays blocked by vi, held boot packages and
unverified deployment prerequisites even when metadata resolution succeeds.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from arm_package_plan import index_repositories, protected
from package_audit import desc_fields, repository_records


def parse_transaction(stdout, packages):
    resolved = []
    for line in stdout.splitlines():
        fields = line.split("\t")
        if len(fields) != 4:
            raise ValueError("unexpected pacman print output")
        name, version, repository, filename = fields
        if protected(name):
            raise ValueError("pacman selected a protected package despite holds")
        row = packages.get((repository, name, version, filename))
        if row is None or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"] or ""):
            raise ValueError("resolved package lacks matching exact repository digest")
        resolved.append(row)
    return resolved


def resolve(review, repositories, baseline, output):
    if review.get("schema") != 1 or review.get("architecture") != "aarch64" or review.get("deployable") is not False:
        raise ValueError("requires the non-deployable ARM review plan")
    expected = {row["name"]: row["sha256"] for row in review["repositories"]}
    if [name for name, _ in repositories] != [row["name"] for row in review["repositories"]]:
        raise ValueError("repository order differs from request review")
    for name, path in repositories:
        if not re.fullmatch(r"[a-z0-9-]+", name) or hashlib.sha256(path.read_bytes()).hexdigest() != expected[name]:
            raise ValueError("repository identity changed after request review")
    installed = {}
    for path in baseline.glob("*/desc"):
        row = desc_fields(path.read_text())
        installed[row["NAME"][0]] = {"version": row["VERSION"][0],
            "description_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    for name, pin in review["protected_installed_pins"].items():
        if installed.get(name) != {"version": pin["version"], "description_sha256": pin["description_sha256"]}:
            raise ValueError("protected installed-image baseline changed")
    index, _ = index_repositories(repositories)
    names = list(dict.fromkeys(row["candidate"]["name"] for row in review["resolved_requests"]))
    if not names or any(protected(name) or not re.fullmatch(r"[a-z0-9@_][a-z0-9@._+-]*", name) for name in names):
        raise ValueError("invalid or protected direct request")
    packages = {}
    for repository, path in repositories:
        for row in repository_records(path, []):
            if row.get("ARCH", [""])[0] not in ("aarch64", "any"):
                continue
            key = (repository, row["NAME"][0], row["VERSION"][0], row.get("FILENAME", [None])[0])
            packages[key] = {"repository": repository, "name": key[1], "version": key[2],
                             "filename": key[3], "sha256": row.get("SHA256SUM", [None])[0],
                             "architecture": row["ARCH"][0]}
    output.mkdir(exist_ok=False)
    for directory in ("root", "db", "db/sync", "cache", "gnupg"):
        (output / directory).mkdir(exist_ok=True)
    shutil.copytree(baseline, output / "db/local")
    for name, path in repositories:
        shutil.copyfile(path, output / "db/sync" / f"{name}.db")
    ignored = sorted({row["name"] for row in index.values() if protected(row["name"])}
                     | set(review["protected_installed_pins"]))
    config = output / "pacman.conf"
    contents = "[options]\nArchitecture = aarch64\nSigLevel = Required DatabaseOptional\n"
    for option, directory in (("RootDir", "root"), ("DBPath", "db"), ("CacheDir", "cache"),
                              ("LogFile", "pacman.log"), ("GPGDir", "gnupg")):
        contents += f"{option} = {(output / directory).resolve()}\n"
    contents += "IgnorePkg = " + " ".join(ignored) + "\n"
    for name, _ in repositories:
        contents += f"\n[{name}]\nServer = https://invalid.example/analysis-only\n"
    config.write_text(contents)
    command = ["pacman", "--config", str(config), "--noconfirm", "--needed", "--print",
               "--print-format", "%n\t%v\t%r\t%f", "-S", "--", *names]
    version = subprocess.run(["pacman", "--version"], env={"PATH": "/usr/bin:/bin", "LANG": "C"},
                             capture_output=True, text=True, timeout=10, check=True)
    run = subprocess.run(command, env={"PATH": "/usr/bin:/bin", "LANG": "C"},
                         capture_output=True, text=True, timeout=45, check=False)
    (output / "stdout.txt").write_text(run.stdout)
    (output / "stderr.txt").write_text(run.stderr)
    result = {"schema": 1, "status": "BLOCKED", "deployable": False, "actions": [],
              "scope": "pacman metadata print resolution of non-protected requests against an immutable image baseline",
              "print_exit": run.returncode, "metadata_resolution": "BLOCKED",
              "requested_candidate_count": len(names), "ignored_packages": ignored,
              "resolver": {"binary_sha256": hashlib.sha256(Path("/usr/bin/pacman").read_bytes()).hexdigest(),
                           "version": next(line.strip() for line in version.stdout.splitlines() if "Pacman v" in line)},
              "request_review_sha256": hashlib.sha256(json.dumps(review, sort_keys=True).encode()).hexdigest(),
              "stdout_sha256": hashlib.sha256(run.stdout.encode()).hexdigest(),
              "stderr_sha256": hashlib.sha256(run.stderr.encode()).hexdigest(),
              "unresolved_original_requests": review["unresolved_requests"],
              "held_original_requests": review["held_requests"],
              "protected_installed_pins": review["protected_installed_pins"],
              "repositories": review["repositories"],
              "remaining_deployment_gates":
                  (["original requests unresolved"] if review["unresolved_requests"] else [])
                  + (["boot/firmware requests held"] if review["held_requests"] else [])
                  + ["complete transaction package signatures and installed hooks unverified",
                     "live target hardware, active experimental driver ABI and tested recovery unverified"],
              "install_command": None, "full_upgrade_authorized": False}
    if run.returncode == 0:
        transaction = parse_transaction(run.stdout, packages)
        selected = {row["name"] for row in transaction}
        skipped = []
        for row in review["resolved_requests"]:
            candidate = row["candidate"]
            if candidate["name"] not in selected:
                installed_version = installed.get(candidate["name"], {}).get("version")
                if installed_version != candidate["version"]:
                    raise ValueError("omitted request is not already installed at reviewed version")
                skipped.append({"name": candidate["name"], "version": installed_version})
        result.update(metadata_resolution="WORKS (print only)", resolved_transaction=transaction,
                      transaction_package_count=len(transaction), already_current_requests=skipped,
                      new_dependency_packages=sorted(selected - set(names)))
    else:
        result["resolver_error"] = run.stderr.replace(str(output.resolve()), "<isolated-review>")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--repository", action="append", required=True, metavar="NAME=DATABASE")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repositories = [(name, Path(path)) for name, path in
                    (argument.split("=", 1) for argument in args.repository)]
    result = resolve(json.loads(args.review.read_text()), repositories, args.database, args.output)
    (args.output / "resolution.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
