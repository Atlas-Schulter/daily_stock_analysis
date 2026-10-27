"""Verify release dependency wiring and real gate CLI exit status without APIs."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


# 同时检查真实发布依赖、同 SHA 构建，以及 Gate CLI 的实际退出码。
class ReleaseGateTests(unittest.TestCase):
    def workflow(self, name):
        return yaml.safe_load((ROOT / '.github/workflows' / name).read_text())

    def test_both_publishers_require_live_gate_for_same_source(self):
        for name, source in [('docker-publish.yml', '${{ needs.resolve-source.outputs.sha }}'),
                             ('ghcr-dockerhub.yml', '${{ github.sha }}')]:
            with self.subTest(workflow=name):
                jobs = self.workflow(name)['jobs']
                gate, publish = jobs['llm-quality'], jobs['build-and-push']
                dependencies = publish['needs']
                self.assertIn('llm-quality', [dependencies] if isinstance(dependencies, str) else dependencies)
                self.assertEqual(gate['uses'], './.github/workflows/llm-release-gate.yml')
                self.assertEqual(gate['with']['source_sha'], source)
                checkout = next(s for s in publish['steps'] if s.get('uses', '').startswith('actions/checkout@'))
                self.assertEqual(checkout['with']['ref'], source)
                self.assertNotIn('if', publish)
                self.assertNotIn('continue-on-error', gate)
                self.assertNotIn('continue-on-error', publish)

    def test_live_gate_is_mandatory_and_cannot_use_rehearsal(self):
        job = self.workflow('llm-release-gate.yml')['jobs']['quality']
        commands = '\n'.join(s.get('run', '') for s in job['steps'])
        self.assertIn('benchmarks.live_v2', commands)
        self.assertIn('--confirm-live', commands)
        self.assertIn('benchmarks.quality_gate --min-pass-rate 1.0', commands)
        self.assertNotIn('rehearse_release_gate', commands)
        for step in job['steps']:
            if 'benchmarks.quality_gate' in step.get('run', '') or 'benchmarks.live_v2' in step.get('run', ''):
                self.assertNotIn('if', step)
                self.assertNotIn('continue-on-error', step)

    # 子进程执行正式 CLI，避免只测内部函数却漏掉命令行退出码。
    def test_valid_and_corrupted_reports_drive_cli_exit_status(self):
        for scenario, code in [('valid', 0), ('invalid', 1)]:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as folder:
                subprocess.run([sys.executable, 'scripts/rehearse_release_gate.py', '--scenario', scenario,
                                '--output', folder], cwd=ROOT, check=True)
                result = subprocess.run([sys.executable, '-m', 'benchmarks.quality_gate',
                                         '--artifacts-dir', folder, '--sample-limit', '2'],
                                        cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                evidence = json.loads((Path(folder) / 'quality_gate.json').read_text())
                self.assertEqual(evidence['passed'], scenario == 'valid')
                if scenario == 'invalid':
                    self.assertTrue(all('mismatch:close' in d['issues'] for d in evidence['details']))

    def test_rehearsal_cannot_publish(self):
        workflow = self.workflow('release-gate-rehearsal.yml')
        self.assertEqual(workflow['permissions'], {'contents': 'read'})
        for job in workflow['jobs'].values():
            for step in job.get('steps', []):
                self.assertNotIn('docker/build-push-action', step.get('uses', ''))


if __name__ == '__main__':
    unittest.main()
