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

from package_audit import desc_fields, package_names, repository_index
from verify_editor_packages import KEYRING_SHA256, SIGNER


PROTECTED = re.compile(
    r"^(linux($|-)|m1n1($|-)|aura($|-)|uboot($|-)|u-boot($|-)|"
    r"limine($|-)|asahi-bless$|asahi-fwextract$|asahi-firmware($|-)|"
    r"apple-firmware($|-)|omarchy-mac($|-)|mkinitcpio($|-)|"
    r"dracut($|-)|grub($|-)|systemd($|-)|mesa$|vulkan-asahi$|libdrm$)")


def protected(name):
    return bool(PROTECTED.match(name) or re.search(r"(^|-)firmware($|-)|-fw$", name))


def index_repositories(repositories):
    return repository_index(repositories, include_payload=True)


def signed_package(proof, candidate, repositories):
    if not candidate:
        return None
    extra_digest = next((row["sha256"] for row in repositories if row["name"] == "extra"), None)
    package = proof.get("packages", {}).get(candidate["name"], {})
    info = package.get("pkginfo", {})
    valid = (proof.get("schema") == 1 and proof.get("database_sha256") == extra_digest
            and proof.get("keyring_sha256") == KEYRING_SHA256
            and proof.get("signer_fingerprint") == SIGNER
            and package.get("signature_valid") is True
            and package.get("signer_fingerprint") == SIGNER
            and package.get("sha256") == candidate["sha256"]
            and package.get("version") == candidate["version"]
            and info.get("pkgver") == [candidate["version"]]
            and info.get("pkgname") == [candidate["name"]] and info.get("arch") == [candidate["architecture"]])
    return package if valid else None


def signed_neovim_alias(proof, candidate, repositories):
    package = signed_package(proof, candidate, repositories)
    return bool(package and candidate["name"] == "neovim" and candidate["architecture"] == "aarch64"
            and "nvim" in package.get("pkginfo", {}).get("provides", [])
            and any(row.get("path") == "usr/bin/nvim" and row.get("type") == "0"
                    and row.get("size", 0) > 0 and row.get("sha256")
                    for row in package.get("bin_entries", [])))


def signed_vi_alias(proof, candidate, repositories, index, execution):
    package = signed_package(proof, candidate, repositories)
    vim = signed_package(proof, index.get("vim"), repositories)
    if not package or not vim or not execution or candidate["name"] != "ex-vi-compat":
        return False
    info = package.get("pkginfo", {})
    wrapper = next((row for row in package.get("bin_entries", []) if row.get("path") == "usr/bin/vi"), {})
    backend = next((row for row in vim.get("bin_entries", []) if row.get("path") == "usr/bin/vim"), {})
    return (candidate["architecture"] == "any" and "vi" in info.get("provides", [])
            and {"bash", "vim"} <= set(info.get("depend", []))
            and wrapper.get("type") == "0" and wrapper.get("mode", 0) & 0o111
            and re.fullmatch(r"[0-9a-f]{64}", wrapper.get("sha256", "")) is not None
            and backend.get("type") == "0" and backend.get("mode", 0) & 0o111
            and re.fullmatch(r"[0-9a-f]{64}", backend.get("sha256", "")) is not None
            and index["vim"]["name"] == "vim"
            and index["vim"]["architecture"] == "aarch64"
            and execution.get("schema") == 1 and execution.get("signer_fingerprint") == SIGNER
            and execution.get("provider_name") == "ex-vi-compat"
            and execution.get("provider_version") == candidate["version"]
            and execution.get("provider_package_sha256") == candidate["sha256"]
            and execution.get("wrapper_sha256") == wrapper["sha256"]
            and execution.get("native_vim_package_sha256") == vim["sha256"]
            and execution.get("native_vim_sha256") == backend.get("sha256")
            and execution.get("compatibility_mode") == 1
            and all(execution.get(key) is True for key in ("vi_invocation_pass", "file_roundtrip_pass",
                                                           "exrc_pass", "exinit_precedence_pass", "edit_save_pass")))


def plan(lists, repositories, local_database, proof, vi_execution=None):
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
            candidate = index.get("vi")
            if not signed_vi_alias(proof, candidate, repo_provenance, index, vi_execution):
                unresolved.append({"requested": request, "reason": "vi requires signed ex-vi-compat ownership/provider proof and matching actual isolated invocation evidence"})
                continue
            name = "ex-vi-compat"
            evidence = "signed ex-vi-compat owns executable usr/bin/vi, provides vi, depends on native vim; unchanged script passed isolated invocation/configuration/edit tests"
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
            "vi_execution_sha256": hashlib.sha256(json.dumps(vi_execution, sort_keys=True).encode()).hexdigest() if vi_execution else None,
            "resolved_requests": resolved, "unresolved_requests": unresolved,
            "held_requests": held, "protected_installed_pins": pins,
            "protected_name_rule": PROTECTED.pattern + " OR (^|-)firmware($|-) OR -fw$",
            "blocked_reasons": reasons, "unattended_reboot_authorized": False,
            "install_command": None, "full_upgrade_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True, help="extracted immutable-image pacman local metadata")
    parser.add_argument("--editor-proof", type=Path, required=True)
    parser.add_argument("--vi-execution", type=Path, help="matching exercise_vi_provider evidence; otherwise vi remains unresolved")
    parser.add_argument("--repository", action="append", required=True, metavar="NAME=DATABASE")
    parser.add_argument("lists", nargs="+", type=Path)
    args = parser.parse_args()
    repositories = [(name, Path(path)) for name, path in
                    (argument.split("=", 1) for argument in args.repository)]
    result = plan(args.lists, repositories, args.database, json.loads(args.editor_proof.read_text()),
                  json.loads(args.vi_execution.read_text()) if args.vi_execution else None)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
