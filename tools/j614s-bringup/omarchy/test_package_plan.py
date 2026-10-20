import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from arm_package_plan import plan, protected
from verify_editor_packages import KEYRING_SHA256, SIGNER, pkginfo_fields, verify_digest
from package_audit import repository_index, repository_records
from resolve_package_review import parse_transaction, resolve
from unittest import mock


class PackagePlanTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.database = self.root / "local"
        self.database.mkdir()
        for name in ("linux-aurora", "m1n1-aurora", "mesa", "asahi-fwextract"):
            path = self.database / (name + "-old")
            path.mkdir()
            (path / "desc").write_text(f"%NAME%\n{name}\n\n%VERSION%\n1-old\n\n%ARCH%\naarch64\n")
        self.repository = self.root / "extra.db"
        with tarfile.open(self.repository, "w:gz") as archive:
            for name, aliases, arch in (("neovim", [], "aarch64"),
                                         ("vim", [], "aarch64"),
                                         ("aura", ["indirect-boot-provider"], "aarch64"),
                                         ("desktop", [], "aarch64"),
                                         ("foreign", [], "x86_64")):
                payload = (f"%NAME%\n{name}\n\n%VERSION%\n2-new\n\n%ARCH%\n{arch}\n\n"
                           f"%FILENAME%\n{name}.pkg.tar.xz\n\n%SHA256SUM%\n{'a' * 64}\n\n%PROVIDES%\n"
                           + "\n".join(aliases) + "\n").encode()
                member = tarfile.TarInfo(name + "/desc")
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
        self.proof = {"schema": 1, "database_sha256": hashlib.sha256(self.repository.read_bytes()).hexdigest(),
                      "keyring_sha256": KEYRING_SHA256, "signer_fingerprint": SIGNER,
                      "packages": {"neovim": {"signature_valid": True, "signer_fingerprint": SIGNER,
                          "version": "2-new", "sha256": "a" * 64,
                          "pkginfo": {"pkgname": ["neovim"], "pkgver": ["2-new"],
                                      "arch": ["aarch64"], "provides": ["nvim"]},
                          "bin_entries": [{"path": "usr/bin/nvim", "type": "0", "size": 10,
                                           "sha256": "b" * 64}]}}}

    def make_plan(self, requests, proof=None):
        source = self.root / "requests.packages"
        source.write_text("\n".join(requests) + "\n")
        return plan([source], [("extra", self.repository)], self.database,
                    self.proof if proof is None else proof)

    def test_signed_nvim_overlay_pins_canonical_neovim(self):
        result = self.make_plan(["nvim"])
        row = result["resolved_requests"][0]
        self.assertEqual(row["resolved"], "neovim")
        self.assertEqual(row["candidate"]["version"], "2-new")
        self.assertEqual(row["candidate"]["sha256"], "a" * 64)
        self.assertFalse(result["deployable"])
        self.assertEqual(result["actions"], [])

    def test_vi_is_not_guessed_from_vim_presence(self):
        result = self.make_plan(["vi"])
        self.assertEqual(result["resolved_requests"], [])
        self.assertEqual(result["unresolved_requests"][0]["requested"], "vi")

    def test_unknown_and_foreign_requests_remain_explicit_failures(self):
        result = self.make_plan(["unknown", "foreign", "desktop"])
        self.assertEqual([row["requested"] for row in result["unresolved_requests"]], ["unknown", "foreign"])
        self.assertEqual(result["resolved_requests"][0]["requested"], "desktop")
        self.assertEqual(result["status"], "BLOCKED")

    def test_boot_requests_and_provider_aliases_are_held(self):
        result = self.make_plan(["linux-aurora", "m1n1-aurora", "mesa", "indirect-boot-provider"])
        self.assertEqual(result["resolved_requests"], [])
        self.assertEqual(len(result["held_requests"]), 4)
        self.assertEqual(result["protected_installed_pins"]["linux-aurora"]["version"], "1-old")
        self.assertFalse(result["full_upgrade_authorized"])
        self.assertIsNone(result["install_command"])

    def test_kernel_firmware_and_boot_names_are_protected(self):
        for name in ("linux-aurora-headers", "m1n1", "aura", "uboot-asahi", "omarchy-mac",
                     "omarchy-mac-boot", "avd-fw", "brcmfmac-firmware", "asahi-fwextract",
                     "mkinitcpio", "systemd", "mesa", "vulkan-asahi"):
            with self.subTest(name=name):
                self.assertTrue(protected(name))
        self.assertFalse(protected("neovim"))

    def test_stale_or_unsigned_editor_evidence_cannot_resolve_alias(self):
        for mutation in ("signature", "database", "package", "keyring", "binary"):
            with self.subTest(mutation=mutation):
                proof = copy.deepcopy(self.proof)
                if mutation == "signature": proof["packages"]["neovim"]["signature_valid"] = False
                elif mutation == "database": proof["database_sha256"] = "0" * 64
                elif mutation == "package": proof["packages"]["neovim"]["sha256"] = "0" * 64
                elif mutation == "keyring": proof["keyring_sha256"] = "0" * 64
                else: proof["packages"]["neovim"]["bin_entries"] = []
                result = self.make_plan(["nvim"], proof)
                self.assertEqual(result["resolved_requests"], [])
                self.assertEqual(result["unresolved_requests"][0]["requested"], "nvim")

    def test_no_baseline_cannot_create_boot_pins(self):
        empty = self.root / "empty"
        empty.mkdir()
        source = self.root / "requests.packages"
        source.write_text("desktop\n")
        with self.assertRaises(ValueError):
            plan([source], [("extra", self.repository)], empty, self.proof)

    def test_tampered_payload_fails_digest_before_inspection(self):
        original = b"signed-archive"
        digest = hashlib.sha256(original).hexdigest()
        self.assertEqual(verify_digest(original, digest), digest)
        with self.assertRaises(ValueError):
            verify_digest(original + b"tampered", digest)

    def test_signed_pkginfo_preserves_multiple_providers_and_dependencies(self):
        result = pkginfo_fields("# generated\npkgname = neovim\nprovides = nvim\nprovides = vim-plugin-runtime\ndepend = glibc\ndepend = libuv\n")
        self.assertEqual(result["provides"], ["nvim", "vim-plugin-runtime"])
        self.assertEqual(result["depend"], ["glibc", "libuv"])

    def test_split_depends_members_provide_repository_alias(self):
        path = self.root / "split.db"
        with tarfile.open(path, "w:gz") as archive:
            for suffix, content in (("depends", "%PROVIDES%\nnvim\n\n%DEPENDS%\nglibc\n"),
                                    ("desc", "%NAME%\nneovim\n\n%VERSION%\n2-new\n\n%ARCH%\naarch64\n")):
                payload = content.encode()
                member = tarfile.TarInfo("neovim-2-new/" + suffix)
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
        records = list(repository_records(path))
        self.assertEqual(records[0]["DEPENDS"], ["glibc"])
        index, _ = repository_index([("extra", path)])
        self.assertEqual(index["nvim"]["name"], "neovim")

    def test_orphan_depends_is_explicitly_reported_and_cannot_resolve(self):
        path = self.root / "orphan.db"
        with tarfile.open(path, "w:gz") as archive:
            payload = b"%DEPENDS%\nglibc\n"
            member = tarfile.TarInfo("orphan-1/depends")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
        with self.assertRaises(ValueError):
            list(repository_records(path))
        index, provenance = repository_index([("extra", path)])
        self.assertEqual(index, {})
        self.assertEqual(provenance[0]["excluded_metadata_entries"][0]["entry"], "orphan-1")

    def test_resolved_protected_dependency_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_transaction("linux-aurora\t2\textra\tkernel.pkg.tar.xz\n", {})

    def test_resolved_payload_must_match_exact_metadata(self):
        key = ("extra", "neovim", "2", "neovim.pkg.tar.xz")
        package = {"name": "neovim", "sha256": "a" * 64}
        self.assertEqual(parse_transaction("neovim\t2\textra\tneovim.pkg.tar.xz\n", {key: package}), [package])
        with self.assertRaises(ValueError):
            parse_transaction("neovim\t3\textra\tneovim.pkg.tar.xz\n", {key: package})
        with self.assertRaises(ValueError):
            parse_transaction("malformed output\n", {})

    def test_changed_repository_rejected_before_any_pacman_subprocess(self):
        review = self.make_plan(["desktop"])
        self.repository.write_bytes(self.repository.read_bytes() + b"changed")
        with mock.patch("resolve_package_review.subprocess.run") as run:
            with self.assertRaises(ValueError):
                resolve(review, [("extra", self.repository)], self.database, self.root / "review")
            run.assert_not_called()

    def test_changed_protected_baseline_rejected_before_any_pacman_subprocess(self):
        review = self.make_plan(["desktop"])
        path = self.database / "linux-aurora-old/desc"
        path.write_text(path.read_text().replace("1-old", "changed"))
        with mock.patch("resolve_package_review.subprocess.run") as run:
            with self.assertRaises(ValueError):
                resolve(review, [("extra", self.repository)], self.database, self.root / "review")
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
