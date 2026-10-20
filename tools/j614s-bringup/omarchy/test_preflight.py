import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tarfile
import unittest
from unittest import mock

from j614s_preflight import collect, cpu_set, evaluate, stage
from package_audit import audit, repository_index


def supported():
    # Synthetic prospective fixture. Not evidence that this hardware works.
    return {"schema": 1, "architecture": "aarch64",
            "compatible": ["apple,j614s", "apple,t6040", "apple,arm-platform"],
            "online_cpus": "0-11", "present_cpus": "0-11", "render_environment": {},
            "render_devices": [{"node": "/dev/dri/renderD128", "driver": "asahi",
                "character_device": True, "probe_exit": 0,
                "probe": {"node": "/dev/dri/renderD128", "renderer": "Apple M4 Pro (G16S B1)",
                          "vendor": "Mesa", "pixel_test": True}}]}


class PreflightTests(unittest.TestCase):
    def collect_fixture(self, value):
        snapshot = copy.deepcopy(value)
        for device in snapshot["render_devices"]:
            device.pop("probe", None)
            device.pop("probe_exit", None)
        return snapshot

    def test_probe_not_started_before_identity_and_environment_guards(self):
        changes = (("architecture", "x86_64"),
                   ("compatible", ["apple,j713", "apple,t8132"]),
                   ("compatible", ["apple,j614s", "apple,t8122"]),
                   ("online_cpus", "0"), ("present_cpus", "0-10"),
                   ("online_cpus", "0-10,15"),
                   ("render_environment", {"LIBGL_ALWAYS_SOFTWARE": "true"}))
        for key, value in changes:
            with self.subTest(key=key, value=value):
                snapshot = self.collect_fixture(supported())
                snapshot[key] = value
                with mock.patch("j614s_preflight.collect_metadata", return_value=snapshot), \
                        mock.patch("j614s_preflight.subprocess.run") as run:
                    collected = collect(Path("render_probe"))
                    run.assert_not_called()
                self.assertFalse(evaluate(collected)["ready_to_stage"])

    def test_probe_not_started_for_inappropriate_node(self):
        for key, value in (("driver", "vgem"), ("driver", "g16_bootstrap"),
                           ("character_device", False), ("node", "/dev/dri/card0")):
            with self.subTest(key=key, value=value):
                snapshot = self.collect_fixture(supported())
                snapshot["render_devices"][0][key] = value
                with mock.patch("j614s_preflight.collect_metadata", return_value=snapshot), \
                        mock.patch("j614s_preflight.subprocess.run") as run:
                    collect(Path("render_probe"))
                    run.assert_not_called()

    def test_qualified_metadata_allows_bound_probe(self):
        expected = supported()
        snapshot = self.collect_fixture(expected)
        output = subprocess.CompletedProcess([], 0, json.dumps(expected["render_devices"][0]["probe"]), "")
        with mock.patch("j614s_preflight.collect_metadata", return_value=snapshot), \
                mock.patch("j614s_preflight.subprocess.run", return_value=output) as run:
            result = collect(Path("render_probe"))
            run.assert_called_once_with([str(Path("render_probe").resolve()), "/dev/dri/renderD128"],
                                        capture_output=True, text=True, timeout=30, check=False)
        self.assertTrue(evaluate(result)["ready_to_stage"])

    def test_prospective_supported_snapshot(self):
        result = evaluate(supported())
        self.assertTrue(result["ready_to_stage"])
        self.assertEqual(result["compositor_acceleration"], "UNTESTED")
        self.assertEqual(result["persistent_installation"], "UNTESTED")

    def test_fake_render_nodes_are_rejected(self):
        for driver in ("vgem", "simple-framebuffer", "simpledrm", "g16_bootstrap", "virtio_gpu", ""):
            with self.subTest(driver=driver):
                value = supported()
                value["render_devices"][0]["driver"] = driver
                self.assertFalse(evaluate(value)["ready_to_stage"])

    def test_software_renderer_does_not_pass_with_asahi_node(self):
        for renderer in ("llvmpipe (LLVM 23)", "Apple M4 Pro (llvmpipe)",
                         "Apple M4 Pro softpipe", "zink Vulkan 1.4 (lavapipe)", "Apple M4 Pro virgl"):
            with self.subTest(renderer=renderer):
                value = supported()
                value["render_devices"][0]["probe"]["renderer"] = renderer
                self.assertFalse(evaluate(value)["ready_to_stage"])

    def test_mismatched_model_and_soc(self):
        for compatible in (["apple,j713", "apple,t8132"], ["apple,j614s", "apple,t8122"],
                           ["apple,t6040"], ["apple,j614s"]):
            value = supported()
            value["compatible"] = compatible
            self.assertFalse(evaluate(value)["ready_to_stage"])

    def test_non_native_architecture(self):
        value = supported()
        value["architecture"] = "x86_64"
        self.assertFalse(evaluate(value)["ready_to_stage"])

    def test_single_core_or_missing_secondary_blocks(self):
        for online in ("4", "0-10", "0-11,15", "bad", "0-999999999"):
            value = supported()
            value["online_cpus"] = online
            self.assertFalse(evaluate(value)["ready_to_stage"])

    def test_wrong_twelve_cpu_ids_block(self):
        value = supported()
        value["online_cpus"] = value["present_cpus"] = "0-10,15"
        self.assertFalse(evaluate(value)["ready_to_stage"])

    def test_probe_must_be_bound_to_actual_node_and_succeed(self):
        for key, data in (("character_device", False), ("probe_exit", 1)):
            value = supported()
            value["render_devices"][0][key] = data
            self.assertFalse(evaluate(value)["ready_to_stage"])
        for key, data in (("pixel_test", False), ("node", "/dev/dri/renderD129"), ("renderer", "Apple M4")):
            value = supported()
            value["render_devices"][0]["probe"][key] = data
            self.assertFalse(evaluate(value)["ready_to_stage"])

    def test_no_transport_only_success(self):
        value = supported()
        value["render_devices"] = []
        value["bootstrap_state"] = "RTKIT_READY protocol=12 rendering=unimplemented"
        self.assertFalse(evaluate(value)["ready_to_stage"])

    def test_ambiguous_multiple_qualified_nodes_block(self):
        value = supported()
        value["render_devices"].append(copy.deepcopy(value["render_devices"][0]))
        self.assertFalse(evaluate(value)["ready_to_stage"])

    def test_software_overrides_block_even_real_device(self):
        value = supported()
        value["render_environment"] = {"LIBGL_ALWAYS_SOFTWARE": "true"}
        self.assertFalse(evaluate(value)["ready_to_stage"])

    def test_rejected_stage_creates_nothing(self):
        value = supported()
        value["render_devices"] = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "new-profile"
            with self.assertRaises(ValueError):
                stage(value, evaluate(value), output)
            self.assertFalse(output.exists())

    def test_staging_never_overwrites_existing_directory(self):
        value = supported()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "review"
            stage(value, evaluate(value), output)
            manifest = json.loads((output / "profile.json").read_text())
            self.assertFalse(manifest["release_authorized"])
            self.assertEqual(manifest["actions"], [])
            with self.assertRaises(FileExistsError):
                stage(value, evaluate(value), output)

    def test_replayed_snapshot_cannot_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "fixture.json"
            source.write_text(json.dumps(supported()))
            destination = Path(directory) / "review"
            run = subprocess.run([sys.executable, str(Path(__file__).with_name("j614s_preflight.py")),
                                  "--snapshot", str(source), "--stage", str(destination)],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertFalse(destination.exists())

    def test_noncontiguous_cpu_set(self):
        self.assertEqual(cpu_set("0-3,8,10-11"), {0, 1, 2, 3, 8, 10, 11})


class PackageAuditTests(unittest.TestCase):
    def test_arm_packages_virtual_providers_and_wrong_arch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, arch, provides in (("neovim", "aarch64", "nvim=1"), ("pc-only", "x86_64", "")):
                path = root / name
                path.mkdir()
                (path / "desc").write_text(f"%NAME%\n{name}\n\n%VERSION%\n1\n\n%ARCH%\n{arch}\n\n%PROVIDES%\n{provides}\n")
            packages = root / "base.packages"
            packages.write_text("nvim # virtual\nneovim\npc-only\nmissing\n")
            result = audit(root, [packages])
            rows = result["lists"][0]
            self.assertEqual(rows["missing_count"], 2)
            self.assertEqual(rows["packages"][0]["installed_as"][0]["name"], "neovim")
            self.assertIn("UNTESTED", result["repository_availability"])

    def test_repository_order_and_architecture_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            repositories = []
            for repo, name, arch in (("overlay", "patched", "aarch64"),
                                     ("foreign", "wrong", "x86_64"),
                                     ("base", "stock", "aarch64")):
                path = Path(directory) / f"{repo}.db"
                payload = f"%NAME%\n{name}\n\n%VERSION%\n1\n\n%ARCH%\n{arch}\n\n%PROVIDES%\nvirtual=1\n".encode()
                with tarfile.open(path, "w:gz") as archive:
                    member = tarfile.TarInfo(f"{name}-1/desc")
                    member.size = len(payload)
                    archive.addfile(member, io.BytesIO(payload))
                repositories.append((repo, path))
            index, provenance = repository_index(repositories)
            self.assertEqual(index["virtual"]["name"], "patched")
            self.assertNotIn("wrong", index)
            self.assertEqual(len(provenance), 3)


if __name__ == "__main__":
    unittest.main()
