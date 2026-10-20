#!/usr/bin/env python3
"""Invoke signed /usr/bin/vi in an isolated namespace with verified ARM Vim.

The official wrapper is unchanged. Only its /usr/bin/vim backend is mapped to
a QEMU dispatch shim in the disposable namespace; no host path is replaced.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

from exercise_editor_payloads import EMULATOR_SHA256
from verify_editor_packages import KEYRING_SHA256, SIGNER, verify_digest


def exercise(payloads, sysroot, output):
    emulator = Path("/usr/bin/qemu-aarch64-static")
    verify_digest(emulator.read_bytes(), EMULATOR_SHA256)
    proof = json.loads((payloads / "inspection.json").read_text())
    keyring = sysroot / "usr/share/pacman/keyrings/archlinuxarm.gpg"
    verify_digest(keyring.read_bytes(), KEYRING_SHA256)
    output.mkdir(exist_ok=False)
    home = output / "gnupg"
    home.mkdir(mode=0o700)
    ring = output / "archlinuxarm-binary.gpg"
    subprocess.run(["gpg", "--homedir", str(home), "--batch", "--dearmor",
                    "--output", str(ring), str(keyring)], check=True)
    executables = {}
    for name, archive_path in (("ex-vi-compat", "usr/bin/vi"), ("vim", "usr/bin/vim")):
        package_record = proof["packages"][name]
        package = payloads / package_record["url"].rsplit("/", 1)[1]
        verify_digest(package.read_bytes(), package_record["sha256"])
        checked = subprocess.run(["gpgv", "--homedir", str(home), "--status-fd", "1",
                                  "--keyring", str(ring.resolve()), str(package) + ".sig", str(package)],
                                 capture_output=True, text=True, check=False)
        if (checked.returncode or f"[GNUPG:] VALIDSIG {SIGNER} " not in checked.stdout
                or any(token in checked.stdout for token in ("EXPKEYSIG", "EXPSIG", "REVKEYSIG", "BADSIG", "ERRSIG"))):
            raise ValueError("vi provider/backend signature recheck failed")
        with tarfile.open(package) as archive:
            member = archive.getmember(archive_path)
            if not member.isfile() or not member.mode & 0o111:
                raise ValueError("required signed executable is absent or not executable")
            content = archive.extractfile(member).read()
        destination = output / name
        destination.write_bytes(content)
        destination.chmod(0o755)
        executables[name] = {"path": destination, "sha256": hashlib.sha256(content).hexdigest()}
    shim = output / "qemu-vim-dispatch"
    shim.write_text('#!/usr/bin/bash\nprintf "%s\\0" "$@" > /work/backend-argv\n'
                    'exec /usr/bin/qemu-aarch64-static -L /arm /payload/vim "$@"\n')
    shim.chmod(0o755)
    work = output / "scratch"
    work.mkdir()
    for directory in ("home", "tmp"):
        (work / directory).mkdir()
    command = ["bwrap", "--unshare-user", "--uid", "0", "--gid", "0", "--unshare-net", "--unshare-pid",
               "--tmpfs", "/", "--dir", "/usr", "--dir", "/usr/bin", "--ro-bind", "/usr/lib", "/usr/lib",
               "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib", "/lib64",
               "--ro-bind", "/usr/bin/bash", "/usr/bin/bash",
               "--ro-bind", "/usr/bin/mktemp", "/usr/bin/mktemp", "--ro-bind", "/usr/bin/rm", "/usr/bin/rm",
               "--ro-bind", str(emulator), str(emulator),
               "--ro-bind", str(executables["ex-vi-compat"]["path"].resolve()), "/usr/bin/vi",
               "--ro-bind", str(shim.resolve()), "/usr/bin/vim",
               "--ro-bind", str(executables["vim"]["path"].resolve()), "/payload/vim",
               "--ro-bind", str((sysroot / "usr/lib").resolve()), "/arm/usr/lib",
               "--symlink", "usr/lib", "/arm/lib", "--bind", str(work.resolve()), "/work",
               "--dev", "/dev", "--proc", "/proc", "--chdir", "/work", "--clearenv",
               "--setenv", "PATH", "/usr/bin", "--setenv", "HOME", "/work/home",
               "--setenv", "TMPDIR", "/work/tmp", "--setenv", "LANG", "C"]
    results = []

    def invoke(name, arguments, extra_env=()):
        extra = [part for key, value in extra_env for part in ("--setenv", key, value)]
        child = subprocess.run([*command, *extra, "--", "/usr/bin/vi", *arguments],
                               capture_output=True, text=True, timeout=30, check=False)
        if child.returncode:
            raise ValueError(f"actual vi invocation failed: {name}: {child.stderr[:512]}")
        argv = (work / "backend-argv").read_bytes().split(b"\0")[:-1]
        backend_args = [item.decode() for item in argv]
        if backend_args[:2] != ["-C", "-u"]:
            raise ValueError("official vi wrapper did not select compatible Vim mode")
        results.append({"case": name, "exit": child.returncode, "backend_arguments": backend_args,
                        "stdout": child.stdout.splitlines()[:4]})

    invoke("version", ["--version"])
    invoke("compatible-roundtrip", ["-i", "NONE", "-n", "-es", "-c",
            'call writefile(["vi-roundtrip", string(&compatible)], "/work/roundtrip.txt")', "-c", "qa!"])
    if (work / "roundtrip.txt").read_text() != "vi-roundtrip\n1\n":
        raise ValueError("vi compatibility mode or file roundtrip failed")
    (work / "home/.exrc").write_text("let g:vi_probe = 6140\n")
    invoke("home-exrc", ["-i", "NONE", "-n", "-es", "-c",
            'call writefile([string(g:vi_probe)], "/work/exrc.txt")', "-c", "qa!"])
    if (work / "exrc.txt").read_text() != "6140\n":
        raise ValueError("official vi HOME/.exrc handling failed")
    invoke("exinit-precedence", ["-i", "NONE", "-n", "-es", "-c",
            'call writefile([string(g:vi_probe)], "/work/exinit.txt")', "-c", "qa!"],
           [("EXINIT", "let g:vi_probe = 6040")])
    if (work / "exinit.txt").read_text() != "6040\n":
        raise ValueError("official vi EXINIT precedence failed")
    (work / "home/.exrc").unlink()
    (work / "edit.txt").write_text("before\n")
    invoke("edit-save", ["-i", "NONE", "-n", "-es", "/work/edit.txt", "-c", "%s/before/after/", "-c", "wq"])
    if (work / "edit.txt").read_text() != "after\n":
        raise ValueError("actual vi edit/save invocation failed")
    provider = proof["packages"]["ex-vi-compat"]
    result = {"schema": 1, "status": "WORKS (isolated invocation only)",
              "scope": "unmodified signed /usr/bin/vi script with QEMU-dispatched signed ARM Vim in a user/mount/network namespace",
              "provider_name": "ex-vi-compat", "provider_version": provider["version"],
              "provider_package_sha256": provider["sha256"], "wrapper_sha256": executables["ex-vi-compat"]["sha256"],
              "native_vim_package_sha256": proof["packages"]["vim"]["sha256"],
              "native_vim_sha256": executables["vim"]["sha256"],
              "emulator_sha256": EMULATOR_SHA256, "signer_fingerprint": SIGNER,
              "vi_invocation_pass": True, "compatibility_mode": 1, "file_roundtrip_pass": True,
              "exrc_pass": True, "exinit_precedence_pass": True, "edit_save_pass": True,
              "cases": results, "host_installation": False, "target_access": False,
              "target_native_execution": "UNTESTED"}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payloads", type=Path, required=True)
    parser.add_argument("--sysroot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = exercise(args.payloads, args.sysroot, args.output)
    (args.output / "vi-execution.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
