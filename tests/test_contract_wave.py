from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.contract_wave import (
    DEFAULT_SPINE_VERSION,
    build_lineage_manifest,
    classify_completed_lineage_step,
    current_spine_version,
    delete_common_requirement,
    delete_spine_checkpoint,
    lineage_manifest_summary_payload,
    load_common_requirements_state,
    load_lineage_manifest_payloads,
    load_lineage_manifests,
    load_spine_state,
    manifest_symbol_inventory_paths,
    normalize_execution_step_policy,
    persist_lineage_completion_artifacts,
    record_manual_spine_checkpoint,
    save_lineage_manifest,
    set_common_requirement_status,
    update_common_requirement,
    update_spine_checkpoint,
    update_contract_wave_artifacts_for_completion,
)
from jakal_flow.errors import ContractWavePersistenceError, PromotionRollbackError
from jakal_flow.git_ops import GitCommandError
from jakal_flow.models import ExecutionPlanState, ExecutionStep, LineageState, RuntimeOptions
from jakal_flow.orchestrator import Orchestrator
from jakal_flow.workspace import WorkspaceManager


class ContractWaveTests(unittest.TestCase):
    def test_execution_step_from_dict_hydrates_policy_fields_from_metadata(self) -> None:
        step = ExecutionStep.from_dict(
            {
                "step_id": "ST1",
                "title": "Shared contract pass",
                "metadata": {
                    "step_type": "contract",
                    "scope_class": "shared_reviewed",
                    "spine_version": "spine-v4",
                    "shared_contracts": ["api.user", "schema.profile"],
                    "verification_profile": "contracts",
                    "promotion_class": "yellow",
                    "primary_scope_paths": ["src/contracts"],
                    "shared_reviewed_paths": ["src/shared"],
                    "forbidden_core_paths": ["src/core"],
                },
            }
        )

        self.assertEqual(step.step_type, "contract")
        self.assertEqual(step.scope_class, "shared_reviewed")
        self.assertEqual(step.spine_version, "spine-v4")
        self.assertEqual(step.shared_contracts, ["api.user", "schema.profile"])
        self.assertEqual(step.primary_scope_paths, ["src/contracts"])
        self.assertEqual(step.shared_reviewed_paths, ["src/shared"])
        self.assertEqual(step.forbidden_core_paths, ["src/core"])

    def test_execution_plan_state_loads_legacy_payload_without_policy_fields(self) -> None:
        state = ExecutionPlanState.from_dict(
            {
                "title": "Legacy plan",
                "tasks": [
                    {
                        "step_id": "ST1",
                        "task_title": "Legacy feature",
                        "display_description": "Keep old plans readable.",
                        "depends_on": "ST0",
                        "owned_paths": "src/app.py, tests/test_app.py",
                    }
                ],
            }
        )

        self.assertEqual(len(state.steps), 1)
        self.assertEqual(state.steps[0].owned_paths, ["src/app.py", "tests/test_app.py"])
        normalize_execution_step_policy(state.steps[0])
        self.assertEqual(state.steps[0].step_type, "feature")
        self.assertEqual(state.steps[0].scope_class, "free_owned")
        self.assertEqual(state.steps[0].primary_scope_paths, ["src/app.py", "tests/test_app.py"])

    def test_guarded_overlap_classifier_green_yellow_red(self) -> None:
        green_step = normalize_execution_step_policy(
            ExecutionStep(
                step_id="ST1",
                title="Leaf feature",
                owned_paths=["src/feature"],
            )
        )
        green = classify_completed_lineage_step(
            green_step,
            changed_files=["src/feature/module.py"],
            verification_passed=True,
            batch_size=1,
            child_count=0,
        )
        self.assertEqual(green.promotion_class, "green")
        self.assertTrue(green.auto_promote_eligible)

        yellow_step = normalize_execution_step_policy(
            ExecutionStep(
                step_id="ST2",
                title="Shared helper pass",
                owned_paths=["src/feature"],
                shared_reviewed_paths=["src/shared"],
            )
        )
        yellow = classify_completed_lineage_step(
            yellow_step,
            changed_files=["src/shared/helper.py"],
            verification_passed=True,
            batch_size=1,
            child_count=0,
        )
        self.assertEqual(yellow.promotion_class, "yellow")
        self.assertFalse(yellow.auto_promote_eligible)

        red_step = normalize_execution_step_policy(
            ExecutionStep(
                step_id="ST3",
                title="Core touch",
                owned_paths=["src/feature"],
                forbidden_core_paths=["src/core"],
            )
        )
        red = classify_completed_lineage_step(
            red_step,
            changed_files=["src/core/runtime.py"],
            verification_passed=True,
            batch_size=1,
            child_count=0,
        )
        self.assertEqual(red.promotion_class, "red")
        self.assertFalse(red.auto_promote_eligible)

    def test_normalize_execution_step_policy_removes_forbidden_scope_that_overlaps_allowed_paths(self) -> None:
        step = normalize_execution_step_policy(
            ExecutionStep(
                step_id="ST1",
                title="Contract bootstrap",
                owned_paths=["cow/kernel/riscv.h", "cow/kernel/defs.h"],
                shared_reviewed_paths=["cow/kernel/riscv.h", "cow/kernel/defs.h"],
                forbidden_core_paths=["cow/kernel"],
                step_type="contract",
                scope_class="shared_reviewed",
            )
        )

        self.assertEqual(step.primary_scope_paths, ["cow/kernel/riscv.h", "cow/kernel/defs.h"])
        self.assertEqual(step.forbidden_core_paths, [])
        self.assertEqual(step.metadata.get("forbidden_core_paths"), [])

    def test_can_auto_promote_lineage_step_requires_green_assessment(self) -> None:
        orchestrator = Orchestrator(Path.cwd() / ".tmp_contract_wave_workspace")
        step = ExecutionStep(step_id="ST1", title="Leaf feature")

        green = classify_completed_lineage_step(
            normalize_execution_step_policy(ExecutionStep(step_id="ST1", title="Leaf feature", owned_paths=["src/feature"])),
            changed_files=["src/feature/module.py"],
            verification_passed=True,
            batch_size=1,
            child_count=0,
        )
        yellow = classify_completed_lineage_step(
            normalize_execution_step_policy(
                ExecutionStep(step_id="ST1", title="Shared pass", owned_paths=["src/feature"], shared_reviewed_paths=["src/shared"])
            ),
            changed_files=["src/shared/module.py"],
            verification_passed=True,
            batch_size=1,
            child_count=0,
        )

        self.assertTrue(orchestrator._can_auto_promote_lineage_step(step, {"ST1": 0}, batch_size=1, assessment=green))
        self.assertFalse(orchestrator._can_auto_promote_lineage_step(step, {"ST1": 0}, batch_size=1, assessment=yellow))

    def test_contract_wave_artifacts_persist_spine_crr_and_manifest(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_contract_wave_artifacts"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        manager = WorkspaceManager(workspace_root)
        context = manager.initialize_local_project(
            project_dir=repo_dir,
            branch="main",
            runtime=RuntimeOptions(model="gpt-5.4", effort="medium"),
        )

        try:
            step = normalize_execution_step_policy(
                ExecutionStep(
                    step_id="ST9",
                    title="Contract wave",
                    owned_paths=["src/contracts"],
                    step_type="contract",
                    scope_class="shared_reviewed",
                    shared_contracts=["api.user"],
                    shared_reviewed_paths=["src/shared"],
                    spine_version=current_spine_version(context.paths),
                )
            )
            assessment = classify_completed_lineage_step(
                step,
                changed_files=["src/contracts/user_contract.py", "src/shared/adapter.py"],
                verification_passed=True,
                batch_size=1,
                child_count=0,
            )
            manifest = build_lineage_manifest(
                lineage_id="LN1",
                step=step,
                changed_files=["src/contracts/user_contract.py", "src/shared/adapter.py"],
                diff_entries=[("A", "src/helpers/contract_helper.py"), ("M", "src/contracts/user_contract.py")],
                verification_command="python -m pytest tests/test_contracts.py",
                verification_summary="contracts passed",
                verification_passed=True,
                assessment=assessment,
                commit_hash="ln1-head",
            )
            _spine, _requirements, crr = update_contract_wave_artifacts_for_completion(
                context.paths,
                step=step,
                lineage_id="LN1",
                manifest=manifest,
                assessment=assessment,
            )
            manifest_path = save_lineage_manifest(context.paths, manifest)

            spine_state = load_spine_state(context.paths.spine_file)
            common_state = load_common_requirements_state(context.paths.common_requirements_file)
            manifests = load_lineage_manifests(context.paths, lineage_id="LN1")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertTrue(manifest_path.name.endswith(".json"))
        self.assertNotEqual(spine_state.current_version, DEFAULT_SPINE_VERSION)
        self.assertEqual(len(spine_state.history), 1)
        self.assertIsNotNone(crr)
        self.assertEqual(len(common_state.open_requirements), 1)
        self.assertEqual(common_state.open_requirements[0].request_id, crr.request_id)
        self.assertEqual(len(manifests), 1)
        self.assertEqual(manifests[0].new_helpers_added, ["src/helpers/contract_helper.py"])
        self.assertEqual(manifests[0].promotion_class, "yellow")

    def test_persist_lineage_completion_artifacts_rolls_back_when_manifest_write_fails(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_contract_wave_manifest_failure"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        manager = WorkspaceManager(workspace_root)
        context = manager.initialize_local_project(
            project_dir=repo_dir,
            branch="main",
            runtime=RuntimeOptions(model="gpt-5.4", effort="medium"),
        )

        try:
            step = normalize_execution_step_policy(
                ExecutionStep(
                    step_id="ST13",
                    title="Contract manifest rollback",
                    owned_paths=["src/contracts"],
                    step_type="contract",
                    scope_class="shared_reviewed",
                    shared_contracts=["api.rollback"],
                    shared_reviewed_paths=["src/shared"],
                    spine_version=current_spine_version(context.paths),
                )
            )
            assessment = classify_completed_lineage_step(
                step,
                changed_files=["src/contracts/rollback_contract.py", "src/shared/adapter.py"],
                verification_passed=True,
                batch_size=1,
                child_count=0,
            )
            manifest = build_lineage_manifest(
                lineage_id="LN13",
                step=step,
                changed_files=["src/contracts/rollback_contract.py", "src/shared/adapter.py"],
                diff_entries=[("M", "src/contracts/rollback_contract.py")],
                verification_command="python -m pytest tests/test_contracts.py",
                verification_summary="contracts passed",
                verification_passed=True,
                assessment=assessment,
                commit_hash="ln13-head",
            )
            with mock.patch(
                "jakal_flow.contract_wave.save_lineage_manifest",
                side_effect=ContractWavePersistenceError("manifest denied"),
            ):
                with self.assertRaisesRegex(ContractWavePersistenceError, "Contract-wave state was rolled back"):
                    persist_lineage_completion_artifacts(
                        context.paths,
                        step=step,
                        lineage_id="LN13",
                        manifest=manifest,
                        assessment=assessment,
                    )
            spine_state = load_spine_state(context.paths.spine_file)
            common_state = load_common_requirements_state(context.paths.common_requirements_file)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(spine_state.current_version, DEFAULT_SPINE_VERSION)
        self.assertEqual(spine_state.history, [])
        self.assertEqual(common_state.open_requirements, [])

    def test_persist_lineage_completion_artifacts_reuses_loaded_state(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_contract_wave_manifest_loads"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        manager = WorkspaceManager(workspace_root)
        context = manager.initialize_local_project(
            project_dir=repo_dir,
            branch="main",
            runtime=RuntimeOptions(model="gpt-5.4", effort="medium"),
        )

        try:
            step = normalize_execution_step_policy(
                ExecutionStep(
                    step_id="ST14",
                    title="Contract state reuse",
                    owned_paths=["src/contracts"],
                    step_type="contract",
                    scope_class="shared_reviewed",
                    shared_contracts=["api.reuse"],
                    shared_reviewed_paths=["src/shared"],
                    spine_version=current_spine_version(context.paths),
                )
            )
            assessment = classify_completed_lineage_step(
                step,
                changed_files=["src/contracts/reuse.py", "src/shared/adapter.py"],
                verification_passed=True,
                batch_size=1,
                child_count=0,
            )
            manifest = build_lineage_manifest(
                lineage_id="LN14",
                step=step,
                changed_files=["src/contracts/reuse.py", "src/shared/adapter.py"],
                diff_entries=[("M", "src/contracts/reuse.py")],
                verification_command="python -m pytest tests/test_reuse.py",
                verification_summary="reuse passed",
                verification_passed=True,
                assessment=assessment,
                commit_hash="ln14-head",
            )
            original_load_spine_state = load_spine_state
            original_load_common_requirements_state = load_common_requirements_state
            with mock.patch(
                "jakal_flow.contract_wave.load_spine_state",
                side_effect=original_load_spine_state,
            ) as load_spine_mock, mock.patch(
                "jakal_flow.contract_wave.load_common_requirements_state",
                side_effect=original_load_common_requirements_state,
            ) as load_common_mock:
                persist_lineage_completion_artifacts(
                    context.paths,
                    step=step,
                    lineage_id="LN14",
                    manifest=manifest,
                    assessment=assessment,
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(load_spine_mock.call_count, 1)
        self.assertEqual(load_common_mock.call_count, 1)

    def test_manifest_symbol_inventory_paths_filters_to_symbol_sensitive_files(self) -> None:
        paths = manifest_symbol_inventory_paths(
            ["README.md", "src/helpers/util.py", "src/api/contracts.ts", "assets/logo.svg"],
            diff_entries=[
                ("M", "README.md"),
                ("M", "src/helpers/util.py"),
                ("M", "src/api/contracts.ts"),
                ("M", "assets/logo.svg"),
            ],
        )

        self.assertEqual(paths, ["src/helpers/util.py", "src/api/contracts.ts"])

    def test_lineage_manifest_payload_limit_uses_latest_items_and_summary_counts_all(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_contract_wave_manifest_cache"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        manager = WorkspaceManager(workspace_root)
        context = manager.initialize_local_project(
            project_dir=repo_dir,
            branch="main",
            runtime=RuntimeOptions(model="gpt-5.4", effort="medium"),
        )

        try:
            first_step = normalize_execution_step_policy(ExecutionStep(step_id="ST1", title="First", owned_paths=["src/first"]))
            first = build_lineage_manifest(
                lineage_id="LN1",
                step=first_step,
                changed_files=["src/first/a.py"],
                diff_entries=[("M", "src/first/a.py")],
                verification_command="python -m pytest",
                verification_summary="first",
                verification_passed=True,
                assessment=classify_completed_lineage_step(
                    first_step,
                    changed_files=["src/first/a.py"],
                    verification_passed=True,
                    batch_size=1,
                    child_count=0,
                ),
                commit_hash="c1",
            )
            first.created_at = "2026-03-29T01:00:00+00:00"
            first.manifest_id = "MAN-1"
            first.promotion_class = "green"
            save_lineage_manifest(context.paths, first)

            second_step = normalize_execution_step_policy(
                ExecutionStep(
                    step_id="ST2",
                    title="Second",
                    owned_paths=["src/second"],
                    shared_reviewed_paths=["src/shared"],
                )
            )
            second = build_lineage_manifest(
                lineage_id="LN2",
                step=second_step,
                changed_files=["src/shared/b.py"],
                diff_entries=[("M", "src/shared/b.py")],
                verification_command="python -m pytest",
                verification_summary="second",
                verification_passed=True,
                assessment=classify_completed_lineage_step(
                    second_step,
                    changed_files=["src/shared/b.py"],
                    verification_passed=True,
                    batch_size=1,
                    child_count=0,
                ),
                commit_hash="c2",
            )
            second.created_at = "2026-03-29T02:00:00+00:00"
            second.manifest_id = "MAN-2"
            save_lineage_manifest(context.paths, second)

            latest_payload = load_lineage_manifest_payloads(context.paths, limit=1, newest_first=True)
            summary = lineage_manifest_summary_payload(context.paths)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(len(latest_payload), 1)
        self.assertEqual(latest_payload[0]["manifest_id"], "MAN-2")
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["green_count"], 1)
        self.assertEqual(summary["yellow_count"], 1)
        self.assertEqual(summary["latest_manifest"]["manifest_id"], "MAN-2")

    def test_build_lineage_manifest_tracks_symbol_level_changes(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_contract_wave_symbols"
        shutil.rmtree(temp_root, ignore_errors=True)
        repo_dir = temp_root / "repo"
        (repo_dir / "src" / "api").mkdir(parents=True, exist_ok=True)
        (repo_dir / "src" / "helpers").mkdir(parents=True, exist_ok=True)
        (repo_dir / "src" / "api" / "contracts.py").write_text(
            "\n".join(
                [
                    "class UserContract(BaseModel):",
                    "    pass",
                    "",
                    "def fetch_user(user_id, include_profile):",
                    "    return user_id",
                    "",
                    "def create_user(payload):",
                    "    return payload",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (repo_dir / "src" / "helpers" / "contract_helper.py").write_text(
            "\n".join(
                [
                    "def normalize_contract(payload):",
                    "    return payload",
                    "",
                    "def format_contract(payload, version):",
                    "    return payload",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        try:
            step = normalize_execution_step_policy(
                ExecutionStep(
                    step_id="ST10",
                    title="Evolve the public contract",
                    owned_paths=["src/api/contracts.py", "src/helpers/contract_helper.py"],
                    shared_contracts=["api.user"],
                    step_type="contract",
                    scope_class="shared_reviewed",
                )
            )
            assessment = classify_completed_lineage_step(
                step,
                changed_files=["src/api/contracts.py", "src/helpers/contract_helper.py"],
                verification_passed=True,
                batch_size=1,
                child_count=0,
            )
            manifest = build_lineage_manifest(
                lineage_id="LN7",
                step=step,
                changed_files=["src/api/contracts.py", "src/helpers/contract_helper.py"],
                diff_entries=[
                    ("M", "src/api/contracts.py"),
                    ("M", "src/helpers/contract_helper.py"),
                ],
                repo_dir=repo_dir,
                previous_file_texts={
                    "src/api/contracts.py": "\n".join(
                        [
                            "class UserContract:",
                            "    pass",
                            "",
                            "def fetch_user(user_id):",
                            "    return user_id",
                            "",
                            "def delete_user(user_id):",
                            "    return user_id",
                            "",
                        ]
                    ),
                    "src/helpers/contract_helper.py": "\n".join(
                        [
                            "def normalize_contract(payload):",
                            "    return payload",
                            "",
                        ]
                    ),
                },
                verification_command="python -m pytest tests/test_contracts.py",
                verification_summary="contracts passed",
                verification_passed=True,
                assessment=assessment,
                commit_hash="ln7-head",
            )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertTrue(any("+function create_user(payload)" in item for item in manifest.public_symbol_changes))
        self.assertTrue(any("-function delete_user(user_id)" in item for item in manifest.public_symbol_changes))
        self.assertTrue(any("~function fetch_user(user_id) -> function fetch_user(user_id, include_profile)" in item for item in manifest.public_symbol_changes))
        self.assertTrue(any("+function format_contract(payload, version)" in item for item in manifest.helper_symbol_changes))

    def test_set_common_requirement_status_moves_record_between_open_and_resolved(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_contract_wave_status_ops"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        manager = WorkspaceManager(workspace_root)
        context = manager.initialize_local_project(
            project_dir=repo_dir,
            branch="main",
            runtime=RuntimeOptions(model="gpt-5.4", effort="medium"),
        )
        context.paths.common_requirements_file.write_text(
            """{
  "updated_at": "2026-03-29T00:00:00+00:00",
  "open_requirements": [
    {
      "request_id": "CRR7",
      "status": "open",
      "created_at": "2026-03-29T00:00:00+00:00",
      "title": "Shared adapter review",
      "reason": "Touches shared adapter",
      "promotion_class": "yellow",
      "step_id": "ST2",
      "lineage_id": "LN2",
      "spine_version": "spine-v3",
      "shared_contracts": ["api.payments"]
    }
  ],
  "resolved_requirements": []
}""",
            encoding="utf-8",
        )

        try:
            _spine, resolved_state, resolved = set_common_requirement_status(
                context.paths,
                request_id="CRR7",
                status="resolved",
                note="resolved by operator",
            )
            _spine, reopened_state, reopened = set_common_requirement_status(
                context.paths,
                request_id="CRR7",
                status="open",
                note="needs another pass",
            )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(len(resolved_state.open_requirements), 0)
        self.assertEqual(len(resolved_state.resolved_requirements), 1)
        self.assertEqual(resolved.status, "resolved")
        self.assertTrue(resolved.resolved_at)
        self.assertIn("resolved by operator", resolved.notes)
        self.assertEqual(len(reopened_state.open_requirements), 1)
        self.assertEqual(len(reopened_state.resolved_requirements), 0)
        self.assertEqual(reopened.status, "open")
        self.assertIsNone(reopened.resolved_at)
        self.assertIn("needs another pass", reopened.notes)

    def test_record_manual_spine_checkpoint_updates_current_version_and_markdown(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_contract_wave_manual_checkpoint"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        manager = WorkspaceManager(workspace_root)
        context = manager.initialize_local_project(
            project_dir=repo_dir,
            branch="main",
            runtime=RuntimeOptions(model="gpt-5.4", effort="medium"),
        )

        try:
            spine_state, _requirements, checkpoint = record_manual_spine_checkpoint(
                context.paths,
                version="spine-v9",
                notes="Operator checkpoint before integration review",
                shared_contracts=["api.payments", "schema.invoice"],
                touched_files=["src/shared/payment_adapter.py"],
                step_id="ST-OPS",
                lineage_id="LN-OPS",
                commit_hash="ops-head",
            )
            shared_contracts_text = context.paths.shared_contracts_file.read_text(encoding="utf-8")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(spine_state.current_version, "spine-v9")
        self.assertEqual(spine_state.history[-1].version, "spine-v9")
        self.assertEqual(checkpoint.lineage_id, "LN-OPS")
        self.assertIn("api.payments", checkpoint.shared_contracts)
        self.assertIn("schema.invoice", shared_contracts_text)
        self.assertIn("spine-v9", shared_contracts_text)
        self.assertTrue(checkpoint.checkpoint_id)

    def test_update_and_delete_common_requirement_write_audit_log(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_contract_wave_crr_mutations"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        manager = WorkspaceManager(workspace_root)
        context = manager.initialize_local_project(
            project_dir=repo_dir,
            branch="main",
            runtime=RuntimeOptions(model="gpt-5.4", effort="medium"),
        )
        context.paths.common_requirements_file.write_text(
            """{
  "updated_at": "2026-03-29T00:00:00+00:00",
  "open_requirements": [
    {
      "request_id": "CRR11",
      "status": "open",
      "created_at": "2026-03-29T00:00:00+00:00",
      "title": "Old title",
      "reason": "Old reason",
      "promotion_class": "yellow",
      "step_id": "ST11",
      "lineage_id": "LN11",
      "spine_version": "spine-v2",
      "affected_paths": ["src/old.py"],
      "shared_contracts": ["api.old"]
    }
  ],
  "resolved_requirements": []
}""",
            encoding="utf-8",
        )

        try:
            _spine, updated_state, updated = update_common_requirement(
                context.paths,
                request_id="CRR11",
                title="Payments review",
                reason="Updated shared adapter scope",
                notes="operator edit",
                affected_paths=["src/payments/adapter.py"],
                shared_contracts=["api.payments"],
                promotion_class="red",
            )
            _spine, deleted_state, deleted = delete_common_requirement(
                context.paths,
                request_id="CRR11",
                note="duplicate request",
            )
            audit_text = context.paths.contract_wave_audit_file.read_text(encoding="utf-8")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(updated.title, "Payments review")
        self.assertEqual(updated.reason, "Updated shared adapter scope")
        self.assertEqual(updated.affected_paths, ["src/payments/adapter.py"])
        self.assertEqual(updated.promotion_class, "red")
        self.assertEqual(len(updated_state.open_requirements), 1)
        self.assertEqual(len(deleted_state.open_requirements), 0)
        self.assertEqual(deleted.request_id, "CRR11")
        self.assertIn('"action": "update"', audit_text)
        self.assertIn('"action": "delete"', audit_text)
        self.assertIn('"entity_type": "common_requirement"', audit_text)

    def test_update_and_delete_spine_checkpoint_write_audit_log(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_contract_wave_checkpoint_mutations"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        manager = WorkspaceManager(workspace_root)
        context = manager.initialize_local_project(
            project_dir=repo_dir,
            branch="main",
            runtime=RuntimeOptions(model="gpt-5.4", effort="medium"),
        )

        try:
            _spine, _requirements, checkpoint = record_manual_spine_checkpoint(
                context.paths,
                version="spine-v5",
                notes="Initial note",
                shared_contracts=["api.payments"],
                touched_files=["src/payments/adapter.py"],
                step_id="ST5",
                lineage_id="LN5",
                commit_hash="head-5",
            )
            _spine, updated_requirements, updated = update_spine_checkpoint(
                context.paths,
                checkpoint_id=checkpoint.checkpoint_id,
                version="spine-v6",
                notes="Edited note",
                shared_contracts=["api.payments", "schema.invoice"],
                touched_files=["src/payments/adapter.py", "src/schema/invoice.py"],
                step_id="ST6",
                lineage_id="LN6",
                commit_hash="head-6",
            )
            _spine, deleted_requirements, deleted = delete_spine_checkpoint(
                context.paths,
                checkpoint_id=checkpoint.checkpoint_id,
                note="superseded by later checkpoint",
            )
            audit_text = context.paths.contract_wave_audit_file.read_text(encoding="utf-8")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(updated.version, "spine-v6")
        self.assertEqual(updated.lineage_id, "LN6")
        self.assertIn("schema.invoice", updated.shared_contracts)
        self.assertTrue(updated_requirements.updated_at)
        self.assertEqual(deleted.checkpoint_id, checkpoint.checkpoint_id)
        self.assertTrue(deleted_requirements.updated_at)
        self.assertIn('"entity_type": "spine_checkpoint"', audit_text)
        self.assertIn('"action": "update"', audit_text)
        self.assertIn('"action": "delete"', audit_text)

    def test_update_common_requirement_rolls_back_when_audit_append_fails(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_contract_wave_crr_audit_failure"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        manager = WorkspaceManager(workspace_root)
        context = manager.initialize_local_project(
            project_dir=repo_dir,
            branch="main",
            runtime=RuntimeOptions(model="gpt-5.4", effort="medium"),
        )
        context.paths.common_requirements_file.write_text(
            """{
  "updated_at": "2026-03-29T00:00:00+00:00",
  "open_requirements": [
    {
      "request_id": "CRR12",
      "status": "open",
      "created_at": "2026-03-29T00:00:00+00:00",
      "title": "Original title",
      "reason": "Original reason",
      "promotion_class": "yellow",
      "step_id": "ST12",
      "lineage_id": "LN12",
      "spine_version": "spine-v2",
      "affected_paths": ["src/original.py"],
      "shared_contracts": ["api.original"]
    }
  ],
  "resolved_requirements": []
}""",
            encoding="utf-8",
        )

        try:
            with mock.patch("jakal_flow.contract_wave.append_jsonl", side_effect=OSError("audit denied")):
                with self.assertRaisesRegex(ContractWavePersistenceError, "State changes were rolled back"):
                    update_common_requirement(
                        context.paths,
                        request_id="CRR12",
                        title="Edited title",
                        reason="Edited reason",
                        shared_contracts=["api.edited"],
                    )
            requirements_state = load_common_requirements_state(context.paths.common_requirements_file)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(requirements_state.open_requirements[0].title, "Original title")
        self.assertEqual(requirements_state.open_requirements[0].reason, "Original reason")
        self.assertEqual(requirements_state.open_requirements[0].shared_contracts, ["api.original"])

    def test_record_manual_spine_checkpoint_rolls_back_when_audit_append_fails(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_contract_wave_checkpoint_audit_failure"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        manager = WorkspaceManager(workspace_root)
        context = manager.initialize_local_project(
            project_dir=repo_dir,
            branch="main",
            runtime=RuntimeOptions(model="gpt-5.4", effort="medium"),
        )

        try:
            with mock.patch("jakal_flow.contract_wave.append_jsonl", side_effect=OSError("audit denied")):
                with self.assertRaisesRegex(ContractWavePersistenceError, "State changes were rolled back"):
                    record_manual_spine_checkpoint(
                        context.paths,
                        version="spine-v7",
                        notes="checkpoint that should roll back",
                        shared_contracts=["api.rollback"],
                    )
            spine_state = load_spine_state(context.paths.spine_file)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(spine_state.current_version, DEFAULT_SPINE_VERSION)
        self.assertEqual(spine_state.history, [])

    def test_allocate_lineage_requires_explicit_join_for_multiple_dependencies(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_contract_wave_join_guard"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        context = orchestrator.workspace.initialize_local_project(
            project_dir=repo_dir,
            branch="main",
            runtime=RuntimeOptions(model="gpt-5.4", effort="medium"),
        )
        plan_state = ExecutionPlanState(
            execution_mode="parallel",
            steps=[
                ExecutionStep(step_id="ST1", title="A"),
                ExecutionStep(step_id="ST2", title="B"),
                ExecutionStep(step_id="ST3", title="Illegal merge", depends_on=["ST1", "ST2"]),
            ],
        )

        try:
            with self.assertRaisesRegex(RuntimeError, "explicit join or barrier"):
                orchestrator._allocate_lineage_for_step(context, plan_state, plan_state.steps[2], {}, {})
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def test_yellow_lineage_step_skips_immediate_promotion(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_contract_wave_yellow_skip"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest", execution_mode="parallel")

        try:
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            context.metadata.current_safe_revision = "safe-main"
            context.loop_state.current_safe_revision = "safe-main"
            orchestrator.workspace.save_project(context)
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(
                            step_id="ST1",
                            title="Shared adapter work",
                            owned_paths=["src/feature"],
                            shared_reviewed_paths=["src/shared"],
                            scope_class="shared_reviewed",
                        ),
                        ExecutionStep(step_id="ST2", title="Completed sibling", status="completed", metadata={"lineage_id": "LN2"}),
                        ExecutionStep(
                            step_id="ST3",
                            title="Join shared work",
                            depends_on=["ST1", "ST2"],
                            metadata={"step_kind": "join", "merge_from": ["ST1", "ST2"], "join_policy": "all"},
                        ),
                    ],
                ),
            )
            orchestrator._save_lineage_states(
                context,
                {
                    "LN2": LineageState(
                        lineage_id="LN2",
                        branch_name="jakal-flow-lineage-ln2",
                        worktree_dir=temp_root / "ln2" / "repo",
                        project_root=temp_root / "ln2",
                        created_at="2026-03-29T00:00:00+00:00",
                        updated_at="2026-03-29T00:00:00+00:00",
                        head_commit="ln2-head",
                        safe_revision="ln2-head",
                        status="merged",
                        merged_by_step_id="ST0",
                    ),
                },
            )
            worker_result = {
                "step_id": "ST1",
                "status": "completed",
                "notes": "shared work complete",
                "commit_hash": "ln1-step",
                "changed_files": ["src/shared/adapter.py"],
                "pass_log": {"pass_type": "block-search-pass"},
                "block_log": {"status": "completed"},
                "test_summary": "shared work complete",
                "head_commit": "ln1-head",
                "ml_report_payload": {},
            }

            with mock.patch.object(orchestrator, "setup_local_project", return_value=context), mock.patch.object(
                orchestrator.git,
                "add_worktree",
            ), mock.patch.object(
                orchestrator,
                "_parallel_worker_count",
                return_value=1,
            ), mock.patch.object(
                orchestrator,
                "_build_lineage_context",
                return_value=mock.Mock(name="yellow-lineage"),
            ), mock.patch.object(
                orchestrator,
                "_run_lineage_step_worker",
                return_value=worker_result,
            ), mock.patch.object(
                orchestrator,
                "_promote_lineage_to_target_branch",
            ) as mocked_promote, mock.patch.object(
                orchestrator,
                "_push_if_ready",
                return_value=(False, "already_up_to_date"),
            ):
                project, saved, steps = orchestrator.run_parallel_execution_batch(
                    project_dir=repo_dir,
                    runtime=runtime,
                    step_ids=["ST1"],
                )
                manifests = load_lineage_manifests(project.paths)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(saved.steps[0].promotion_class, "yellow")
        self.assertEqual(steps[0].commit_hash, "ln1-step")
        mocked_promote.assert_not_called()
        self.assertEqual(len(manifests), 1)
        self.assertEqual(manifests[0].promotion_class, "yellow")

    def test_promote_lineage_to_target_branch_rolls_back_on_push_failure(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_contract_wave_promotion_failure"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        context = orchestrator.workspace.initialize_local_project(
            project_dir=repo_dir,
            branch="main",
            runtime=RuntimeOptions(model="gpt-5.4", effort="medium"),
        )
        context.metadata.current_safe_revision = "safe-main"
        context.loop_state.current_safe_revision = "safe-main"
        lineage = LineageState(
            lineage_id="LN1",
            branch_name="jakal-flow-lineage-ln1",
            worktree_dir=temp_root / "ln1" / "repo",
            project_root=temp_root / "ln1",
            created_at="2026-03-29T00:00:00+00:00",
            updated_at="2026-03-29T00:00:00+00:00",
            head_commit="ln1-head",
            safe_revision="ln1-head",
        )

        try:
            with mock.patch.object(orchestrator.git, "merge_ff_only"), mock.patch.object(
                orchestrator.git,
                "current_revision",
                return_value="main-promoted",
            ), mock.patch.object(
                orchestrator,
                "_push_if_ready",
                return_value=(False, "push_failed:network"),
            ), mock.patch.object(
                orchestrator.git,
                "hard_reset",
            ) as mocked_reset:
                promoted, reason, commit_hash = orchestrator._promote_lineage_to_target_branch(context, lineage)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertFalse(promoted)
        self.assertEqual(reason, "push_failed:network")
        self.assertIsNone(commit_hash)
        mocked_reset.assert_called_once_with(context.paths.repo_dir, "safe-main")
        self.assertEqual(context.metadata.current_safe_revision, "safe-main")
        self.assertEqual(context.loop_state.current_safe_revision, "safe-main")

    def test_promote_lineage_to_target_branch_raises_when_rollback_fails(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_contract_wave_promotion_rollback_failure"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        context = orchestrator.workspace.initialize_local_project(
            project_dir=repo_dir,
            branch="main",
            runtime=RuntimeOptions(model="gpt-5.4", effort="medium"),
        )
        context.metadata.current_safe_revision = "safe-main"
        context.loop_state.current_safe_revision = "safe-main"
        lineage = LineageState(
            lineage_id="LN2",
            branch_name="jakal-flow-lineage-ln2",
            worktree_dir=temp_root / "ln2" / "repo",
            project_root=temp_root / "ln2",
            created_at="2026-03-29T00:00:00+00:00",
            updated_at="2026-03-29T00:00:00+00:00",
            head_commit="ln2-head",
            safe_revision="ln2-head",
        )

        try:
            with mock.patch.object(orchestrator.git, "merge_ff_only"), mock.patch.object(
                orchestrator.git,
                "current_revision",
                return_value="main-promoted",
            ), mock.patch.object(
                orchestrator,
                "_push_if_ready",
                return_value=(False, "push_failed:network"),
            ), mock.patch.object(
                orchestrator.git,
                "hard_reset",
                side_effect=GitCommandError("reset failed"),
            ):
                with self.assertRaisesRegex(PromotionRollbackError, "Failed to restore safe revision"):
                    orchestrator._promote_lineage_to_target_branch(context, lineage)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(context.metadata.current_safe_revision, "main-promoted")
        self.assertEqual(context.loop_state.current_safe_revision, "main-promoted")


if __name__ == "__main__":
    unittest.main()
