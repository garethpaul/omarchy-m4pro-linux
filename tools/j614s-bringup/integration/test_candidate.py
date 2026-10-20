import copy
import json
import os
from pathlib import Path
import unittest

from validate_candidate import check_invariants, validate

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get('J614S_CANDIDATE_SOURCE', str(HERE.parents[1] / 'overnight-gravity-j614s')))
LEDGER = json.loads((HERE / 'port-ledger.json').read_text())
CONFIG = HERE / 'configs/j614s-gravity-candidate.config'


def snapshot():
    files = {row['path']: (SOURCE / row['path']).read_text() for row in LEDGER['files']}
    settings = dict(line.split('=', 1) for line in CONFIG.read_text().splitlines()
                    if line.startswith('CONFIG_') and '=' in line)
    return files, settings


class CandidateTests(unittest.TestCase):
    def test_actual_clean_checkpoint(self):
        result = validate(SOURCE, CONFIG, LEDGER)
        self.assertIs(result['deployment_allowed'], False)
        self.assertEqual(result['hardware'], 'UNTESTED')
        self.assertTrue(result['storage'].startswith('BLOCKED'))

    def test_config_digest_is_bound(self):
        ledger = copy.deepcopy(LEDGER)
        ledger['config_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'config digest'): validate(SOURCE, CONFIG, ledger)

    def test_source_commit_is_bound(self):
        ledger = copy.deepcopy(LEDGER)
        ledger['candidate_commit'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'source commit'): validate(SOURCE, CONFIG, ledger)

    def test_selected_source_digests_are_bound(self):
        ledger = copy.deepcopy(LEDGER)
        ledger['files'][0]['candidate_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'source digest'): validate(SOURCE, CONFIG, ledger)

    def test_no_single_cpu_or_idle_workaround_command_line(self):
        for field, bad in [('CONFIG_NR_CPUS', '1'), ('CONFIG_CMDLINE', '"idle=nop"'),
                           ('CONFIG_CMDLINE', '"arm64.nowfxt maxcpus=1"'),
                           ('CONFIG_DRM_APPLE', 'y'), ('CONFIG_DRM_ASAHI_M4', 'y')]:
            files, settings = snapshot()
            settings[field] = bad
            with self.subTest(field=field, bad=bad):
                with self.assertRaises(ValueError): check_invariants(files, settings)

    def test_no_unqualified_full_gpu_or_dcp_alias(self):
        for path, alias in [('drivers/gpu/drm/asahi/asahi_m4.rs', 'apple,t6040-gpu'),
                            ('drivers/gpu/drm/apple/dcp.c', 'apple,j614s-dcp')]:
            files, settings = snapshot()
            files[path] += '\nconst char *bad_alias = "' + alias + '";\n'
            with self.subTest(path=path):
                with self.assertRaises(ValueError): check_invariants(files, settings)

    def test_nvme_refusal_precedes_every_hardware_operation(self):
        for operation in ['reset_control_assert(anv->reset);',
                          'apple_rtkit_wake(anv->rtk);', 'writel(0, anv->mmio_coproc);',
                          'apple_nvme_attach_genpd(anv);']:
            files, settings = snapshot()
            name = 'drivers/nvme/host/apple.c'
            files[name] = files[name].replace('if (of_machine_is_compatible("apple,j614s"))',
                                               operation + '\n\tif (of_machine_is_compatible("apple,j614s"))', 1)
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(ValueError, 'operation before'): check_invariants(files, settings)

    def test_nvme_guard_cannot_be_removed_or_moved_after_allocation(self):
        files, settings = snapshot()
        name = 'drivers/nvme/host/apple.c'
        files[name] = files[name].replace('if (of_machine_is_compatible("apple,j614s"))',
                                         'if (of_machine_is_compatible("apple,j616s"))', 1)
        with self.assertRaisesRegex(ValueError, 'NVMe refusal'): check_invariants(files, settings)
        files, settings = snapshot()
        text = files[name]
        start = text.index('if (of_machine_is_compatible("apple,j614s"))')
        end = text.index('));', start) + 3
        guard = text[start:end]
        text = text[:start] + text[end:]
        allocation = '\tanv = devm_kzalloc(dev, sizeof(*anv), GFP_KERNEL);'
        files[name] = text.replace(allocation, allocation + '\n\t' + guard, 1)
        with self.assertRaisesRegex(ValueError, 'NVMe refusal'): check_invariants(files, settings)

    def test_wfxt_override_must_follow_boot_argument_parse(self):
        files, settings = snapshot()
        name = 'arch/arm64/kernel/pi/idreg-override.c'
        files[name] = files[name].replace('parse_cmdline(fdt, chosen);', '')
        files[name] += '\nparse_cmdline(fdt, chosen);\n'
        with self.assertRaisesRegex(ValueError, 'unsafe timed waits'): check_invariants(files, settings)

    def test_simd_must_be_saved_before_wait(self):
        files, settings = snapshot()
        name = 'arch/arm64/kernel/idle.c'
        files[name] = files[name].replace('fpsimd_save_and_flush_cpu_state();', '')
        files[name] += '\nfpsimd_save_and_flush_cpu_state();\n'
        with self.assertRaisesRegex(ValueError, 'FP/SIMD'): check_invariants(files, settings)

    def test_layout_checks_cannot_be_disabled(self):
        files, settings = snapshot()
        files['rust/Makefile'] += '\n--no-layout-tests\n'
        with self.assertRaisesRegex(ValueError, 'layout assertions'): check_invariants(files, settings)

    def test_bootstrap_cannot_be_called_rendering(self):
        for call in ['drm_dev_register(dev);', 'apple_rtkit_send_message(rtk, 0x20, init, NULL, false);']:
            files, settings = snapshot()
            files['drivers/gpu/drm/asahi/g16-bootstrap.c'] += '\n' + call + '\n'
            with self.subTest(call=call):
                with self.assertRaisesRegex(ValueError, 'rendering/application INIT'): check_invariants(files, settings)


if __name__ == '__main__':
    unittest.main()
