"""Regressions over frozen actual-package evidence; no payload execution."""
import json
from pathlib import Path
import unittest

ABI = Path(__file__).resolve().parents[1]
FINAL = ABI/'coherent-candidate/attempt-03'

def load(path):
    return json.loads(path.read_text())

class SeparateCandidate(unittest.TestCase):
    def test_original_signed117_and_all_holds_preserved(self):
        original = load(ABI.parent/'evidence/configured-current-proposal.json')
        candidate = load(FINAL/'proposal.json')
        selected = {r['name']: r for r in candidate['resolved_transaction']}
        for row in original['resolved_transaction']:
            self.assertEqual(selected[row['name']], row)
        self.assertEqual(candidate['protected_installed_pins'], original['protected_installed_pins'])
        self.assertEqual(candidate['held_original_requests'], original['held_original_requests'])
        self.assertEqual(candidate['transaction_differences']['unchanged_count'], 117)
        self.assertEqual(candidate['transaction_differences']['changed'], [])

    def test_unsigned_source_never_substitutes_signed_nvim(self):
        candidate = load(FINAL/'proposal.json')
        row = next(r for r in candidate['resolved_transaction'] if r['name'] == 'omarchy-nvim')
        self.assertEqual(row['version'], '2026.9.21-5')
        self.assertEqual(candidate['source_candidate']['source_version'], '2026.9.21-6')
        self.assertIn('not built, signed, released or selected', candidate['source_candidate']['status'])
        q = load(FINAL/'configured-current-payload-qualification.json')
        self.assertEqual(q['counts'], {'selected':151, 'payloads_qualified':151, 'failed':0})
        self.assertEqual({r['name'] for r in q['packages']}, {r['name'] for r in candidate['resolved_transaction']})

    def test_normal_prepare_retains_fixed986_and_exact_four_removals(self):
        prep = load(FINAL/'preparation.json')
        self.assertTrue(prep['prepared'])
        self.assertEqual(prep['flags'], 139264)
        self.assertEqual(prep['baseline_description_count'], 986)
        self.assertEqual(prep['baseline_description_digest'], '05592373e5f03cfcfeb32ea3dcf0fb835b307e9e1eae75540e670db36e5e1e7e')
        self.assertEqual({r['name'] for r in prep['remove']}, {'dotnet-host','dotnet-runtime','mise','quickshell-git'})
        for name in ('committed', 'fetch_attempts', 'unexpected_question', 'protected_changed'):
            self.assertFalse(prep[name])

    def test_independent_actual_readelf_proves_coupled_rebuilds(self):
        rows = load(FINAL/'readelf-crosscheck.json')['rows']
        opencv = {r['path'].startswith('baseline/'):r for r in rows if r.get('package') == 'opencv'}
        tiff = {r['path'].startswith('baseline/'):r for r in rows if r.get('package') == 'libtiff'}
        self.assertIn('libOpenEXR-3_4.so.33', opencv[True]['needed'])
        self.assertIn('libOpenEXR-3_5.so.34', opencv[False]['needed'])
        self.assertIn('libjbig.so.2.1', tiff[True]['needed'])
        self.assertIn('libjbig.so.2.2', tiff[False]['needed'])
        self.assertEqual({r['machine'] for r in rows}, {183})
        self.assertEqual(len(rows), 12)

    def test_actual_graph_keeps_gaps_visible(self):
        model = load(FINAL/'filesystem-model.json')
        self.assertEqual(model['counts']['new_or_incoming_issue_edges'], 0)
        self.assertEqual(model['new_or_incoming_issues'], [])
        self.assertEqual(model['counts']['preserved_issue_edges'], 57)
        self.assertEqual(model['counts']['parse_gaps'], 344)
        self.assertEqual(model['counts']['incoming_ELF_machines'], {'183':1581, '62':1})
        self.assertFalse(model['deployable'])
        self.assertFalse(model['execution_ready'])
        interim = load(ABI/'coherent-candidate/attempt-02/filesystem-model.json')
        self.assertEqual(interim['counts']['new_or_incoming_issue_edges'], 6)

if __name__ == '__main__':
    unittest.main()
