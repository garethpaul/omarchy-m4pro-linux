#!/usr/bin/env python3
"""Generate an exact, non-executable ARM package review plan with boot holds.

This is not a dependency solver or installer. Missing requests remain failures;
metadata, even signed editor metadata, cannot authorize boot-chain changes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from package_audit import desc_fields, package_names, repository_records
from verify_editor_packages import KEYRING_SHA256, SIGNER


PROTECTED = re.compile(
    r"^(linux($|-)|m1n1($|-)|aura($|-)|uboot($|-)|u-boot($|-)|"
    r"limine($|-)|asahi-bless$|asahi-fwextract$|asahi-firmware($|-)|"
    r"apple-firmware($|-)|omarchy-mac($|-)|mkinitcpio($|-)|"
    r"dracut($|-)|grub($|-)|systemd($|-)|mesa$|vulkan-asahi$|libdrm$)")


def protected(name):
    return bool(PROTECTED.match(name) or re.search(r"(^|-)firmware($|-)|-fw$", name))


def index_repositories(repositories):
    index = {}
    provenance = []
    for repository, path in repositories:
        diagnostics = []
        provenance.append({"name": repository, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "excluded_metadata_entries": diagnostics})
        for row in repository_records(path, diagnostics):
            if row.get("ARCH", [""])[0] not in ("aarch64", "any"):
                continue
            candidate = {"repository": repository, "name": row["NAME"][0],
                         "version": row["VERSION"][0], "architecture": row["ARCH"][0],
                         "filename": row.get("FILENAME", [None])[0],
                         "sha256": row.get("SHA256SUM", [None])[0]}
            for alias in [candidate["name"], *[entry.split("=", 1)[0] for entry in row.get("PROVIDES", [])]]:
                index.setdefault(alias, candidate)
    return index, provenance


def signed_neovim_alias(proof, candidate, repositories):
    if not candidate:
        return False
    extra_digest = next((row["sha256"] for row in repositories if row["name"] == "extra"), None)
    package = proof.get("packages", {}).get("neovim", {})
    info = package.get("pkginfo", {})
    return (proof.get("schema") == 1 and proof.get("database_sha256") == extra_digest
            and proof.get("keyring_sha256") == KEYRING_SHA256
            and proof.get("signer_fingerprint") == SIGNER
            and package.get("signature_valid") is True
            and package.get("signer_fingerprint") == SIGNER
            and package.get("sha256") == candidate["sha256"]
            and package.get("version") == candidate["version"]
            and candidate["name"] == "neovim" and info.get("pkgver") == [candidate["version"]]
            and info.get("pkgname") == ["neovim"] and info.get("arch") == ["aarch64"]
            and "nvim" in info.get("provides", [])
            and any(row.get("path") == "usr/bin/nvim" and row.get("type") == "0"
                    and row.get("size", 0) > 0 and row.get("sha256")
                    for row in package.get("bin_entries", [])))


def plan(lists, repositories, local_database, proof):
    index, repo_provenance = index_repositories(repositories)
    requests = list(dict.fromkeys(name for path in lists for name in package_names(path)))
    installed = {}
    for path in sorted(local_database.glob("*/desc")):
        row = desc_fields(path.read_text())
        installed[row["NAME"][0]] = {"version": row["VERSION"][0], "architecture": row["ARCH"][0],
                                     "description_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    if not installed:
        raise ValueError("installed baseline metadata is required to pin protected packages")
    pins = {name: values for name, values in installed.items() if protected(name)}
    resolved = []
    unresolved = []
    held = []
    for request in requests:
        if protected(request):
            held.append({"requested": request, "reason": "boot/firmware/system/graphics ABI identity is protected",
                         "installed_pin": installed.get(request)})
            continue
        name = request
        evidence = "repository metadata"
        if request == "nvim":
            if not signed_neovim_alias(proof, index.get("neovim"), repo_provenance):
                unresolved.append({"requested": request, "reason": "canonical neovim requires matching signed payload proof"})
                continue
            name = "neovim"
            evidence = "signed native neovim .PKGINFO provides nvim and archive contains usr/bin/nvim"
        if request == "vi":
            # Verified vim and vim-runtime archives have no vi path or alias.
            # An editor with similar features is not proof of the requested executable.
            unresolved.append({"requested": request, "reason": "verified vim/vim-runtime do not contain usr/bin/vi; no proven native vi resolution"})
            continue
        candidate = index.get(name)
        if candidate is None:
            unresolved.append({"requested": request, "reason": "no native repository candidate"})
            continue
        if protected(candidate["name"]):
            held.append({"requested": request, "candidate": candidate,
                         "reason": "repository provider resolves to protected package"})
            continue
        if not candidate["filename"] or not re.fullmatch(r"[0-9a-f]{64}", candidate["sha256"] or ""):
            unresolved.append({"requested": request, "reason": "candidate lacks exact payload filename/SHA256"})
            continue
        resolved.append({"requested": request, "resolved": name, "candidate": candidate,
                         "resolution_evidence": evidence})
    reasons = ["dependency closure/conflicts/hooks and signatures for the complete transaction remain unverified",
               "live target baseline and exact experimental kernel/firmware artifacts are not established by this image plan",
               "protected packages and their reverse dependencies cannot be modified by this plan"]
    if unresolved:
        reasons.append("one or more requested packages remain unresolved")
    return {"schema": 1, "status": "BLOCKED", "deployable": False, "actions": [],
            "scope": "exact requested-package review pins, not a solved pacman transaction or target mutation",
            "architecture": "aarch64", "sources": [{"list": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in lists],
            "repositories": repo_provenance,
            "editor_proof_sha256": hashlib.sha256(json.dumps(proof, sort_keys=True).encode()).hexdigest(),
            "resolved_requests": resolved, "unresolved_requests": unresolved,
            "held_requests": held, "protected_installed_pins": pins,
            "protected_name_rule": PROTECTED.pattern + " OR (^|-)firmware($|-) OR -fw$",
            "blocked_reasons": reasons, "unattended_reboot_authorized": False,
            "install_command": None, "full_upgrade_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True, help="extracted immutable-image pacman local metadata")
    parser.add_argument("--editor-proof", type=Path, required=True)
    parser.add_argument("--repository", action="append", required=True, metavar="NAME=DATABASE")
    parser.add_argument("lists", nargs="+", type=Path)
    args = parser.parse_args()
    repositories = [(name, Path(path)) for name, path in
                    (argument.split("=", 1) for argument in args.repository)]
    result = plan(args.lists, repositories, args.database, json.loads(args.editor_proof.read_text()))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
