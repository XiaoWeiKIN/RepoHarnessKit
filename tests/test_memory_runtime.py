from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = ROOT / "assets/core/engineering-specs"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old
    return module


class MemoryRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = load(CORE_DIR / "spec_router.py", "memory_runtime_test_router")
        cls.runtime = load(CORE_DIR / "memory_runtime.py", "memory_runtime_test_runtime")
        cls.retrieval = load(CORE_DIR / "memory_retrieval.py", "memory_runtime_test_retrieval")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = self.root / "docs/exec-plans/active/ep-001_background/EXECPLAN.md"
        self.plan.parent.mkdir(parents=True)
        self.plan.write_text(
            '---\nid: EP-001\nstatus: blocked\nadr_refs: []\n---\n'
            '## Current Snapshot\n\nBACKGROUND_SENTINEL ' + '上下文 ' * 80 + '\n'
            '## Progress\n\n- [ ] Unfinished task remains.\n', encoding='utf-8')
        self.config = self.root / self.runtime.CONFIG_PATH
        self.baseline = self.core.plan_session_context((
            self.core.SessionContextSection('rules', 0, 'Protected routing instructions',
                                            'rules.md', mandatory=True),
        ), budget_bytes=2048)

    def configure(self, mode='opt-in', **extra):
        self.config.parent.mkdir(exist_ok=True)
        self.config.write_text(json.dumps({
            'schema_version': 1, 'mode': mode, 'background_ep': ['EP-001'], **extra
        }), encoding='utf-8')

    def apply(self, runtime=None, baseline=None):
        return self.runtime.apply_context(
            self.core, self.root, runtime or {}, baseline or self.baseline,
            as_of='2026-10-29T00:00:00Z')

    def test_absent_config_is_identical_and_does_not_load_modules(self):
        with patch.object(self.runtime, '_selection_module', side_effect=AssertionError('unexpected load')):
            self.assertIs(self.apply(), self.baseline)
        self.assertFalse(self.config.exists())

    def test_explicit_off_does_not_read_report_or_background(self):
        self.configure('off', review_report='missing.json')
        self.plan.unlink()
        with patch.object(self.runtime, '_selection_module', side_effect=AssertionError('unexpected load')):
            result = self.apply()
        self.assertEqual(result['text'], self.baseline['text'])
        self.assertEqual(result['memory']['status'], 'off')

    def test_shadow_and_opt_in_protect_core_and_measure_configured_delta(self):
        self.configure('shadow')
        before = self.plan.read_bytes()
        shadow = self.apply()
        self.assertIn('BACKGROUND_SENTINEL', shadow['text'])
        self.assertEqual(shadow['memory']['saved_bytes'], 0)
        self.configure('opt-in')
        applied = self.apply()
        self.assertNotIn('BACKGROUND_SENTINEL', applied['text'])
        self.assertIn('[ContextRef:memory-', applied['text'])
        self.assertTrue(applied['text'].startswith(self.baseline['text'] + '\n\n'))
        self.assertEqual(applied['selections'][0], self.baseline['selections'][0])
        self.assertEqual(applied['used_bytes'], len(applied['text'].encode('utf-8')))
        self.assertLessEqual(applied['used_bytes'], applied['budget_bytes'])
        self.assertGreater(applied['memory']['saved_bytes'], 0)
        self.assertEqual(applied['memory']['configured_baseline_bytes'], shadow['used_bytes'])
        self.assertEqual(self.plan.read_bytes(), before)
        self.assertFalse(applied['memory']['authority_changed'])

    def test_direct_reference_is_never_reintroduced_as_background(self):
        self.configure()
        result = self.apply({'context_ep_ref': 'EP-001'})
        self.assertEqual(result['text'], self.baseline['text'])
        self.assertEqual(result['memory']['reason'], 'NO_BACKGROUND_CONTEXT')
        promoted = self.apply({'context_direct_ep_refs': ['EP-001', 'EP-002']})
        self.assertIn('BACKGROUND_SENTINEL', promoted['text'])
        self.assertEqual(promoted['memory']['selection'][0]['tier'], 'direct')
        self.assertEqual(promoted['memory']['saved_bytes'], 0)

    def test_ambiguous_large_scope_falls_back(self):
        self.configure()
        result = self.apply({'context_direct_ep_overflow': True})
        self.assertEqual(result['text'], self.baseline['text'])
        self.assertEqual(result['memory']['reason'], 'TASK_SCOPE_TOO_LARGE')

    def test_no_budget_cannot_displace_core(self):
        self.configure()
        full = dict(self.baseline, budget_bytes=self.baseline['used_bytes'])
        result = self.apply(baseline=full)
        self.assertEqual(result['text'], full['text'])
        self.assertEqual(result['memory']['reason'], 'NO_SUPPLEMENTAL_BUDGET')

    def test_tiny_remaining_budget_falls_back_without_weakening_rules(self):
        self.configure()
        full = dict(self.baseline, budget_bytes=self.baseline['used_bytes'] + 8)
        result = self.apply(baseline=full)
        self.assertEqual(result['text'], full['text'])
        self.assertEqual(result['memory']['status'], 'baseline_fallback')

    def test_malformed_config_falls_back(self):
        self.configure()
        for raw in ('{', '[]', '{"schema_version":1,"schema_version":1,"mode":"opt-in"}',
                    '{"schema_version":true,"mode":"opt-in"}',
                    '{"schema_version":1,"mode":"all"}'):
            self.config.write_text(raw, encoding='utf-8')
            result = self.apply()
            self.assertEqual(result['text'], self.baseline['text'])
            self.assertEqual(result['memory']['status'], 'baseline_fallback')

    def test_config_validation_rejects_unsafe_and_unbounded_inputs(self):
        for extra in ({'background_ep': ['EP-001', 'ep-0001']},
                      {'background_ep': ['EP-001'] * 9},
                      {'review_report': '../report.json'},
                      {'review_report': '/report.json'},
                      {'max_report_age_seconds': True}, {'unrecognized': True}):
            with self.subTest(extra=extra), self.assertRaises(self.runtime.MemoryRuntimeError):
                self.runtime.config_from({'schema_version': 1, 'mode': 'opt-in', **extra})

    def test_missing_background_is_nonblocking(self):
        self.configure()
        self.plan.unlink()
        result = self.apply()
        self.assertEqual(result['text'], self.baseline['text'])
        self.assertEqual(result['memory']['status'], 'baseline_fallback')

    def test_symlink_background_is_not_read(self):
        self.configure()
        target = self.root / 'external.md'
        target.write_text('must not load', encoding='utf-8')
        self.plan.unlink()
        self.plan.symlink_to(target)
        result = self.apply()
        self.assertEqual(result['text'], self.baseline['text'])
        self.assertEqual(result['memory']['status'], 'baseline_fallback')

    def test_symlink_config_is_rejected(self):
        self.configure()
        target = self.root / 'external.json'
        target.write_bytes(self.config.read_bytes())
        self.config.unlink()
        self.config.symlink_to(target)
        self.assertEqual(self.apply()['text'], self.baseline['text'])

    def test_source_changes_during_selection_are_not_used(self):
        self.configure()
        original = self.core._session_ep_snapshot
        def changing(*args):
            result = original(*args)
            self.plan.write_text(self.plan.read_text() + '\nExternally changed\n')
            return result
        with patch.object(self.core, '_session_ep_snapshot', side_effect=changing):
            result = self.apply()
        self.assertEqual(result['text'], self.baseline['text'])
        self.assertEqual(result['memory']['reason'], 'SOURCE_CHANGED')

    def write_report(self, stamp='2026-10-29T00:00:00Z', source_hash=None):
        report = {
            'schema_version': 1, 'engine_version': 'memory-review-v1',
            'input_integrity': 'validated', 'read_only': True, 'as_of': stamp,
            'items': [{'kind': 'exec-plan', 'artifact_id': 'EP-001',
                       'assessment': 'review_due',
                       'source': {'path': self.plan.relative_to(self.root).as_posix(),
                                  'sha256': source_hash or self.runtime._digest(self.plan.read_bytes())}}],
        }
        report['report_sha256'] = self.retrieval.sha256(self.retrieval.canonical(report))
        (self.root / 'review.json').write_text(json.dumps(report), encoding='utf-8')

    def test_valid_optional_review_is_annotation_not_authority(self):
        self.configure(review_report='review.json')
        self.write_report()
        result = self.apply()
        self.assertEqual(result['memory']['status'], 'applied')
        self.assertIn('REVIEW_DUE_IS_NOT_EXPIRY', result['memory']['selection'][0]['reason_codes'])
        self.assertFalse(result['memory']['authority_changed'])

    def test_absent_stale_future_and_drifted_report_return_original_core(self):
        self.configure(review_report='review.json')
        self.assertEqual(self.apply()['text'], self.baseline['text'])
        for stamp, digest in (('2020-01-01T00:00:00Z', None),
                              ('2099-01-01T00:00:00Z', None),
                              ('2026-10-29T00:00:00Z', '0' * 64)):
            self.write_report(stamp, digest)
            result = self.apply()
            self.assertEqual(result['text'], self.baseline['text'])
            self.assertEqual(result['memory']['status'], 'baseline_fallback')

    def test_fixed_time_and_sources_replay_identically(self):
        self.configure()
        self.assertEqual(self.apply(), self.apply())


class MemoryRuntimeIntegrationTests(unittest.TestCase):
    def setUp(self):
        from tests.test_spec_router import SpecRouterTestCase
        self.fixture = SpecRouterTestCase()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.repo
        self.plan = self.root / 'docs/exec-plans/active/ep-123_background/EXECPLAN.md'
        self.plan.parent.mkdir(parents=True)
        self.plan.write_text('---\nid: EP-123\nstatus: active\nadr_refs: []\n---\n'
                             '## Current Snapshot\n\nRUNTIME_BACKGROUND ' + 'context ' * 80 + '\n'
                             '## Progress\n\n- [ ] Still unfinished.\n', encoding='utf-8')
        self.config = self.root / '.repo-foundry/memory-context.json'

    def configure(self, mode):
        self.config.write_text(json.dumps({'schema_version': 1, 'mode': mode,
                                           'background_ep': ['EP-123']}), encoding='utf-8')

    def event(self, adapter='portable', event='session_start', prompt='Fix a bounded bug'):
        return json.loads(self.fixture.run_core('event', stdin={
            'protocol_version': 2, 'adapter_id': adapter, 'session_id': 'session-1',
            'turn_id': 'turn-1', 'event': event, 'prompt': prompt,
            'memory_as_of': '2026-10-29T00:00:00Z',
        }).stdout)

    def test_bootstrap_registers_new_assets_but_does_not_enable_cooling(self):
        manifest = json.loads((self.root / 'docs/.engineering/harness.json').read_text())
        self.assertEqual(manifest['core']['version'], '1.6.2')
        paths = {item['path'] for item in manifest['files']}
        for name in ('memory_runtime.py', 'memory_retrieval.py'):
            relative = '.repo-foundry/engineering-specs/' + name
            self.assertIn(relative, paths)
            self.assertTrue((self.root / relative).is_file())
        self.assertFalse(self.config.exists())
        self.assertNotIn('memory', self.event()['context_plan'])
        self.fixture.run_foundry('validate', '--harness')

    def test_codex_native_hook_applies_cooling_and_off_restores_original(self):
        self.configure('shadow')
        shadow = self.fixture.hook('UserPromptSubmit', prompt='Fix a bounded bug')
        self.assertIn('RUNTIME_BACKGROUND', shadow['hookSpecificOutput']['additionalContext'])
        self.configure('opt-in')
        cooled = self.fixture.hook('UserPromptSubmit', prompt='Fix a bounded bug')
        self.assertNotIn('RUNTIME_BACKGROUND', cooled['hookSpecificOutput']['additionalContext'])
        self.assertIn('[ContextRef:memory-', cooled['hookSpecificOutput']['additionalContext'])
        self.configure('off')
        off = self.fixture.hook('UserPromptSubmit', prompt='Fix a bounded bug')
        self.assertNotIn('[ContextRef:memory-', off['hookSpecificOutput']['additionalContext'])
        self.assertIn('Governed mode', off['hookSpecificOutput']['additionalContext'])

    def test_claude_portable_and_codex_share_selection_semantics(self):
        self.configure('opt-in')
        selections = [self.event(adapter)['context_plan']['memory']['selection']
                      for adapter in ('codex', 'claude', 'portable')]
        self.assertEqual(selections[0], selections[1])
        self.assertEqual(selections[1], selections[2])

    def test_explicit_ep_and_subagent_resume_scope_are_protected(self):
        self.configure('opt-in')
        direct = self.event(prompt='Continue EP-123')
        self.assertIn('RUNTIME_BACKGROUND', direct['context'])
        self.assertEqual(direct['context_plan']['memory']['reason'], 'NO_BACKGROUND_CONTEXT')
        resumed = self.event(event='context_resume', prompt='')
        self.assertIn('RUNTIME_BACKGROUND', resumed['context'])
        self.assertEqual(resumed['context_plan']['memory']['reason'], 'NO_BACKGROUND_CONTEXT')

    def test_new_subagent_explicit_reference_cannot_be_cooled_on_resume(self):
        self.configure('opt-in')
        self.event()
        child = self.event(event='subagent_start', prompt='Examine EP-123 and EP-124')
        self.assertIn('RUNTIME_BACKGROUND', child['context'])
        resumed = self.event(event='context_resume', prompt='')
        self.assertIn('RUNTIME_BACKGROUND', resumed['context'])
        self.assertEqual(resumed['context_plan']['memory']['selection'][0]['tier'], 'direct')

    def test_mutation_gate_and_capsule_remain_independent(self):
        self.configure('opt-in')
        self.fixture.initialize_turn()
        blocked = self.fixture.hook('PreToolUse', tool_name='apply_patch', tool_input={
            'command': '*** Begin Patch\n*** Update File: service/main.go\n@@\n-package service\n+package service\n*** End Patch'
        })
        self.assertEqual(blocked['hookSpecificOutput']['permissionDecision'], 'deny')
        self.fixture.activate_go('service/main.go')
        first = json.loads(self.fixture.run_router('rehydrate', '--session-id', 'session-1',
                                                   '--turn-id', 'turn-1').stdout)
        self.configure('off')
        second = json.loads(self.fixture.run_router('rehydrate', '--session-id', 'session-1',
                                                    '--turn-id', 'turn-1').stdout)
        marker = 'Exact activation capsule rehydrated for this context epoch:\n\n'
        self.assertEqual(first['context'].split(marker, 1)[1], second['context'].split(marker, 1)[1])
        self.assertFalse(first['context_plan']['memory']['capsule_budget_included'])

    def test_invalid_baseline_is_not_swallowed_by_optional_runtime(self):
        self.configure('opt-in')
        result = self.fixture.run_core('event', stdin={
            'protocol_version': 2, 'event': 'session_start', 'adapter_id': 'portable',
            'session_id': 'x' * 9000, 'turn_id': 'large', 'prompt': 'Inspect source',
        }, expected=2)
        self.assertIn('ROUTER_SESSION_CONTEXT_BUDGET_EXCEEDED', result.stderr)

    def test_resume_reloads_current_source_without_mutating_documents(self):
        self.configure('opt-in')
        before = {p: p.read_bytes() for p in (self.plan, self.config)}
        first = self.event()
        self.event(event='context_resume', prompt='')
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.plan.write_text(self.plan.read_text().replace('RUNTIME_BACKGROUND', 'CHANGED_BACKGROUND'))
        changed = self.event(event='context_resume', prompt='')
        self.assertNotEqual(first['context_plan']['memory']['sources'],
                            changed['context_plan']['memory']['sources'])

    def test_old_core_file_contract_does_not_require_new_memory_modules(self):
        with patch.object(sys, 'path', [str(ROOT / 'scripts'), *sys.path]):
            foundry = load(ROOT / 'scripts/foundryctl.py', 'memory_runtime_foundry_contract')
        older = {item[0] for item in foundry.versioned_file_assets('1.5.6', ())}
        self.assertNotIn('.repo-foundry/engineering-specs/memory_runtime.py', older)
        self.assertNotIn('.repo-foundry/engineering-specs/memory_retrieval.py', older)
        current = {item[0] for item in foundry.versioned_file_assets('1.6.0', ())}
        self.assertIn('.repo-foundry/engineering-specs/memory_runtime.py', current)


if __name__ == '__main__':
    unittest.main()
