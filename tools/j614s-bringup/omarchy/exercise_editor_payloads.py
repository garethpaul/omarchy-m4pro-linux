#!/usr/bin/env python3
"""Exercise signed ARM editors using the existing, pinned host QEMU only.

All created files live in a new disposable output directory. No package install,
hooks, target connection or native hardware claim. No archive-wide extraction.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

from verify_editor_packages import KEYRING_SHA256, SIGNER, verify_digest

EMULATOR_SHA256 = "66bdc286fd30970a1c3d2029b460605a3dc843ed6b397f4cd9825f9c19551507"


def exercise(payloads, sysroot, output):
    emulator = Path("/usr/bin/qemu-aarch64-static")
    verify_digest(emulator.read_bytes(), EMULATOR_SHA256)
    checked = subprocess.run(["pacman", "-Qkk", "qemu-user-static"],
                             env={"PATH": "/usr/bin:/bin", "LANG": "C"}, capture_output=True,
                             text=True, check=False)
    if checked.returncode or "45 total files, 0 altered files" not in checked.stdout:
        raise ValueError("existing emulator package provenance changed; review before execution")
    proof = json.loads((payloads / "inspection.json").read_text())
    keyring = sysroot / "usr/share/pacman/keyrings/archlinuxarm.gpg"
    verify_digest(keyring.read_bytes(), KEYRING_SHA256)
    output.mkdir(exist_ok=False)
    home = output / "home"
    home.mkdir()
    gpghome = output / "gnupg"
    gpghome.mkdir(mode=0o700)
    ring = output / "archlinuxarm-binary.gpg"
    subprocess.run(["gpg", "--homedir", str(gpghome), "--batch", "--dearmor",
                    "--output", str(ring), str(keyring)], check=True)
    prefix = output / "prefix"
    (prefix / "usr").mkdir(parents=True)
    for link in (prefix / "lib", prefix / "usr/lib"):
        link.symlink_to((sysroot / "usr/lib").resolve(), target_is_directory=True)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home.resolve()), "LANG": "C.UTF-8",
           "XDG_CONFIG_HOME": str((home / "config").resolve()),
           "XDG_DATA_HOME": str((home / "data").resolve()),
           "XDG_STATE_HOME": str((home / "state").resolve()),
           "XDG_CACHE_HOME": str((home / "cache").resolve()),
           "NVIM_LOG_FILE": str((home / "nvim.log").resolve())}
    result = {"schema": 1, "scope": "ARM userspace emulation on build host; not target hardware",
              "emulator": {"package": "qemu-user-static 11.1.2-1", "binary_sha256": EMULATOR_SHA256,
                           "package_file_check": "45 total files, 0 altered files"}, "results": {}}
    for name, executable in (("vim", "vim"), ("neovim", "nvim")):
        record = proof["packages"][name]
        package = payloads / record["url"].rsplit("/", 1)[1]
        verify_digest(package.read_bytes(), record["sha256"])
        checked = subprocess.run(["gpgv", "--homedir", str(gpghome), "--status-fd", "1",
                                  "--keyring", str(ring.resolve()), str(package) + ".sig", str(package)],
                                 capture_output=True, text=True, check=False)
        if (checked.returncode or f"[GNUPG:] VALIDSIG {SIGNER} " not in checked.stdout
                or any(token in checked.stdout for token in ("EXPKEYSIG", "EXPSIG", "REVKEYSIG", "BADSIG", "ERRSIG"))):
            raise ValueError("editor archive signature recheck failed")
        with tarfile.open(package) as archive:
            member = archive.getmember("usr/bin/" + executable)
            if not member.isfile():
                raise ValueError("expected signed editor executable missing")
            content = archive.extractfile(member).read()
        binary = output / executable
        binary.write_bytes(content)
        binary.chmod(0o755)
        prefix_args = [str(emulator), "-L", str(prefix.resolve()), str(binary.resolve())]
        version = subprocess.run([*prefix_args, "--version"], env=env, capture_output=True,
                                 text=True, timeout=20, check=False)
        destination = output / (name + "-roundtrip.txt")
        token = "j614s-arm-editor-roundtrip"
        command = f'call writefile(["{token}"], {json.dumps(str(destination.resolve()))})'
        roundtrip = subprocess.run([*prefix_args, "-u", "NONE", "-i", "NONE", "-n", "-es",
                                    "-c", command, "-c", "qa!"], env=env,
                                   capture_output=True, text=True, timeout=20, check=False)
        passed = roundtrip.returncode == 0 and destination.exists() and destination.read_text() == token + "\n"
        if version.returncode or not passed:
            raise ValueError(f"verified {name} failed ARM emulation check")
        result["results"][name] = {"binary_sha256": hashlib.sha256(content).hexdigest(),
            "version_exit": version.returncode, "version_output": version.stdout.splitlines()[:4],
            "roundtrip_exit": roundtrip.returncode, "roundtrip_pass": passed,
            "command": "qemu-aarch64-static -L ISOLATED_PREFIX VERIFIED_BINARY -u NONE -i NONE -n -es -c call_writefile_owned_scratch -c qa!",
            "usr_bin_vi_available": any(entry.get("path") == "usr/bin/vi"
                for package_record in proof["packages"].values()
                for entry in package_record.get("bin_entries", []))}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payloads", type=Path, required=True)
    parser.add_argument("--sysroot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new disposable directory")
    args = parser.parse_args()
    result = exercise(args.payloads, args.sysroot, args.output)
    (args.output / "execution.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
