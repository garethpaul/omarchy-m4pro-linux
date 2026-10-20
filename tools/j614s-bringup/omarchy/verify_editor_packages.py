#!/usr/bin/env python3
"""Verify official ARM editor archives without installing them or running hooks."""
import argparse
import base64
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import urllib.request

from package_audit import repository_records

KEYRING_SHA256 = "6ce771e853f04a38a5b533cb33e61f877b9b06b58b6db051eb8a15d737a2332f"
SIGNER = "68B3537F39A313B3E574D06777193F152BDBE6A6"
NAMES = ("neovim", "vim", "vim-runtime")


def pkginfo_fields(value):
    result = {}
    for line in value.splitlines():
        if " = " in line and not line.startswith("#"):
            key, field = line.split(" = ", 1)
            result.setdefault(key, []).append(field)
    return result


def verify_digest(data, expected):
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError("package SHA256 mismatch")
    return actual


def inspect(database, keyring, output, names=NAMES, architectures=("aarch64",)):
    keyring_hash = verify_digest(keyring.read_bytes(), KEYRING_SHA256)
    output.mkdir(exist_ok=False)
    home = output / "gnupg"
    home.mkdir(mode=0o700)
    binary_keyring = output / "archlinuxarm-binary.gpg"
    subprocess.run(["gpg", "--homedir", str(home), "--batch", "--dearmor",
                    "--output", str(binary_keyring), str(keyring)], check=True)
    selected = {}
    diagnostics = []
    for fields in repository_records(database, diagnostics):
        if fields.get("NAME", [None])[0] in names:
            selected[fields["NAME"][0]] = fields
    if set(selected) != set(names):
        raise ValueError("required editor metadata missing")
    evidence = {"schema": 1, "database_sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
                "keyring_sha256": keyring_hash,
                "keyring_origin": "re-extracted from verified September OS image; see image-provenance.json",
                "signer_fingerprint": SIGNER,
                "excluded_repository_metadata": diagnostics,
                "package_execution": "UNTESTED by this verifier; never invokes payloads or hooks",
                "packages": {}}
    for name in names:
        fields = selected[name]
        filename = fields["FILENAME"][0]
        if Path(filename).name != filename or fields.get("ARCH", [None])[0] not in architectures:
            raise ValueError("unexpected package filename or architecture")
        url = "https://arm-mirror.omarchy.org/aarch64/extra/" + filename
        with urllib.request.urlopen(url, timeout=40) as response:
            data = response.read(32 * 1024 * 1024 + 1)
        if len(data) != int(fields["CSIZE"][0]) or len(data) > 32 * 1024 * 1024:
            raise ValueError("package size mismatch")
        digest = verify_digest(data, fields["SHA256SUM"][0])
        package = output / filename
        package.write_bytes(data)
        signature = output / f"{filename}.sig"
        signature.write_bytes(base64.b64decode(fields["PGPSIG"][0], validate=True))
        checked = subprocess.run(["gpgv", "--homedir", str(home), "--status-fd", "1",
                                  "--keyring", str(binary_keyring.resolve()), str(signature), str(package)],
                                 capture_output=True, text=True, check=False)
        if checked.returncode or f"[GNUPG:] VALIDSIG {SIGNER} " not in checked.stdout:
            raise ValueError(f"signature validation failed for {name}")
        if any(token in checked.stdout for token in ("EXPKEYSIG", "EXPSIG", "REVKEYSIG", "BADSIG", "ERRSIG")):
            raise ValueError(f"invalid signer state for {name}")
        entries = []
        info = None
        has_install_script = False
        with tarfile.open(package) as archive:
            for member in archive:
                if member.name == ".PKGINFO" and member.isfile():
                    info = pkginfo_fields(archive.extractfile(member).read().decode())
                if member.name == ".INSTALL":
                    has_install_script = True
                if member.name.startswith("usr/bin/"):
                    row = {"path": member.name, "linkname": member.linkname,
                           "type": member.type.decode(), "size": member.size, "mode": member.mode}
                    # Extract only the exact executable, never directories, symlinks or hooks.
                    if member.isfile() and member.name in ("usr/bin/vim", "usr/bin/nvim", "usr/bin/vi"):
                        executable = output / name / member.name
                        executable.parent.mkdir(parents=True, exist_ok=True)
                        content = archive.extractfile(member).read()
                        executable.write_bytes(content)
                        executable.chmod(0o755)
                        row["sha256"] = hashlib.sha256(content).hexdigest()
                    entries.append(row)
        if info is None or info.get("pkgname") != [name] or info.get("arch") != fields.get("ARCH"):
            raise ValueError("signed package identity mismatch")
        if info.get("pkgver") != fields.get("VERSION"):
            raise ValueError("signed package version mismatch")
        evidence["packages"][name] = {"name": name, "version": info["pkgver"][0],
                "architecture": info["arch"][0], "url": url, "sha256": digest, "bytes": len(data),
                "signature_valid": True, "signer_fingerprint": SIGNER,
                "retrieved_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "gpg_status": checked.stdout.splitlines(), "pkginfo": info,
                "has_install_script": has_install_script, "bin_entries": entries}
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--keyring", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new disposable inspection folder")
    parser.add_argument("--include-vi-provider", action="store_true", help="also inspect signed ex-vi-compat (architecture any)")
    args = parser.parse_args()
    evidence = inspect(args.database, args.keyring, args.output,
                       (*NAMES, "ex-vi-compat") if args.include_vi_provider else NAMES,
                       ("aarch64", "any") if args.include_vi_provider else ("aarch64",))
    (args.output / "inspection.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
