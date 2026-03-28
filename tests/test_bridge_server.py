from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jakal_flow.bridge_server import BridgeJobStore
from jakal_flow.utils import read_json, read_jsonl


class BridgeJobStoreTests(unittest.TestCase):
    def test_create_queues_excess_jobs_and_persists_scheduler_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir) / "workspace"
            published: list[dict] = []
            store = BridgeJobStore(lambda envelope: published.append(envelope.to_dict()), max_running_jobs=1)

            running = store.create("run-plan", workspace_root, {"project_dir": str(workspace_root / "repo-a")})
            queued = store.create("run-plan", workspace_root, {"project_dir": str(workspace_root / "repo-b")})

            self.assertEqual(running.status, "running")
            self.assertEqual(queued.status, "queued")
            self.assertTrue(queued.allow_background_queue)
            self.assertEqual(queued.queue_priority, 0)
            self.assertEqual(queued.queue_position, 1)

            state = read_json(workspace_root / "job_scheduler.json", default={}) or {}
            self.assertEqual(state.get("max_concurrent_jobs"), 1)
            self.assertEqual([item.get("status") for item in state.get("jobs", [])], ["running", "queued"])
            self.assertEqual([item.get("queue_priority") for item in state.get("jobs", [])], [0, 0])
            self.assertEqual([item.get("queue_position") for item in state.get("jobs", [])], [0, 1])

            events = read_jsonl(workspace_root / "job_scheduler_events.jsonl")
            self.assertEqual([item.get("event_type") for item in events], ["job-started", "job-queued"])
            self.assertTrue(any(item.get("payload", {}).get("job", {}).get("status") == "queued" for item in published))

    def test_create_rejects_queueing_when_project_reservations_are_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir) / "workspace"
            store = BridgeJobStore(lambda _envelope: None, max_running_jobs=1)

            store.create("run-plan", workspace_root, {"project_dir": str(workspace_root / "repo-a")})

            with self.assertRaisesRegex(RuntimeError, "Reservations are disabled for this project"):
                store.create(
                    "run-plan",
                    workspace_root,
                    {
                        "project_dir": str(workspace_root / "repo-b"),
                        "runtime": {
                            "allow_background_queue": False,
                        },
                    },
                )

    def test_create_orders_queued_jobs_by_higher_project_priority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir) / "workspace"
            store = BridgeJobStore(lambda _envelope: None, max_running_jobs=1)

            running = store.create("run-plan", workspace_root, {"project_dir": str(workspace_root / "repo-a")})
            low = store.create(
                "run-plan",
                workspace_root,
                {
                    "project_dir": str(workspace_root / "repo-low"),
                    "runtime": {"background_queue_priority": -5},
                    "display_name": "Low Priority",
                },
            )
            high = store.create(
                "run-plan",
                workspace_root,
                {
                    "project_dir": str(workspace_root / "repo-high"),
                    "runtime": {"background_queue_priority": 10},
                    "display_name": "High Priority",
                },
            )

            low_snapshot = store.get_job(low.id) or {}
            high_snapshot = store.get_job(high.id) or {}
            self.assertEqual(high_snapshot.get("queue_position"), 1)
            self.assertEqual(high_snapshot.get("queue_priority"), 10)
            self.assertEqual(high_snapshot.get("display_name"), "High Priority")
            self.assertEqual(low_snapshot.get("queue_position"), 2)
            self.assertEqual(low_snapshot.get("queue_priority"), -5)

            store.update(running.id, status="completed", error=None, result={})
            promoted = store.dequeue_startable_jobs(workspace_root)

            self.assertEqual([item.id for item in promoted], [high.id])
            self.assertEqual((store.get_job(low.id) or {}).get("queue_position"), 1)

    def test_duplicate_project_jobs_are_rejected_and_queued_jobs_start_after_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir) / "workspace"
            store = BridgeJobStore(lambda _envelope: None, max_running_jobs=1)

            repo_a = str(workspace_root / "repo-a")
            repo_b = str(workspace_root / "repo-b")
            first = store.create("run-plan", workspace_root, {"project_dir": repo_a})
            second = store.create("run-plan", workspace_root, {"project_dir": repo_b})

            with self.assertRaisesRegex(RuntimeError, "already active for this project"):
                store.create("run-plan", workspace_root, {"project_dir": repo_a})

            store.update(first.id, status="completed", error=None, result={})
            promoted = store.dequeue_startable_jobs(workspace_root)

            self.assertEqual(len(promoted), 1)
            self.assertEqual(promoted[0].id, second.id)
            self.assertEqual(promoted[0].status, "running")
            self.assertEqual(promoted[0].queue_position, 0)

            state = read_json(workspace_root / "job_scheduler.json", default={}) or {}
            self.assertEqual(len(state.get("jobs", [])), 1)
            self.assertEqual(state["jobs"][0]["id"], second.id)
            self.assertEqual(state["jobs"][0]["status"], "running")

    def test_cancel_releases_the_queue_slot_and_updates_scheduler_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir) / "workspace"
            published: list[dict] = []
            store = BridgeJobStore(lambda envelope: published.append(envelope.to_dict()), max_running_jobs=1)

            running = store.create("run-plan", workspace_root, {"project_dir": str(workspace_root / "repo-a")})
            queued_one = store.create("run-plan", workspace_root, {"project_dir": str(workspace_root / "repo-b")})
            queued_two = store.create("run-plan", workspace_root, {"project_dir": str(workspace_root / "repo-c")})

            cancelled = store.cancel(queued_one.id)

            self.assertIsNotNone(cancelled)
            self.assertEqual(cancelled.status, "cancelled")
            self.assertEqual(cancelled.queue_position, 0)

            queued_two_snapshot = store.get_job(queued_two.id) or {}
            self.assertEqual(queued_two_snapshot.get("status"), "queued")
            self.assertEqual(queued_two_snapshot.get("queue_position"), 1)

            state = read_json(workspace_root / "job_scheduler.json", default={}) or {}
            self.assertEqual([item.get("id") for item in state.get("jobs", [])], [running.id, queued_two.id])
            self.assertEqual([item.get("queue_position") for item in state.get("jobs", [])], [0, 1])

            events = read_jsonl(workspace_root / "job_scheduler_events.jsonl")
            self.assertEqual([item.get("event_type") for item in events], ["job-started", "job-queued", "job-queued", "job-cancelled"])
            self.assertTrue(any(item.get("payload", {}).get("job", {}).get("status") == "cancelled" for item in published))

    def test_increasing_concurrency_promotes_queued_jobs_and_updates_scheduler_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir) / "workspace"
            store = BridgeJobStore(lambda _envelope: None, max_running_jobs=1)

            first = store.create("run-plan", workspace_root, {"project_dir": str(workspace_root / "repo-a")})
            second = store.create("run-plan", workspace_root, {"project_dir": str(workspace_root / "repo-b")})
            third = store.create("run-plan", workspace_root, {"project_dir": str(workspace_root / "repo-c")})

            snapshot, promoted = store.set_max_running_jobs(workspace_root, 2)

            self.assertEqual(snapshot.get("max_concurrent_jobs"), 2)
            self.assertEqual([job.get("status") for job in snapshot.get("jobs", [])], ["running", "running", "queued"])
            self.assertEqual(len(promoted), 1)
            self.assertEqual(promoted[0].id, second.id)
            self.assertEqual(promoted[0].status, "running")

            queued_snapshot = store.get_job(third.id) or {}
            self.assertEqual(queued_snapshot.get("status"), "queued")
            self.assertEqual(queued_snapshot.get("queue_position"), 1)

            state = read_json(workspace_root / "job_scheduler.json", default={}) or {}
            self.assertEqual(state.get("max_concurrent_jobs"), 2)
            self.assertEqual(
                [(item.get("id"), item.get("status"), item.get("queue_position")) for item in state.get("jobs", [])],
                [(second.id, "running", 0), (first.id, "running", 0), (third.id, "queued", 1)],
            )

    def test_create_uses_unique_ids_even_with_same_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir) / "workspace"
            store = BridgeJobStore(lambda _envelope: None, max_running_jobs=1)

            with patch("jakal_flow.bridge_server.now_ms", return_value=1234567890):
                first = store.create("run-plan", workspace_root, {"project_dir": str(workspace_root / "repo-a")})
                second = store.create("run-plan", workspace_root, {"project_dir": str(workspace_root / "repo-b")})

            self.assertNotEqual(first.id, second.id)

            state = read_json(workspace_root / "job_scheduler.json", default={}) or {}
            self.assertEqual([item.get("status") for item in state.get("jobs", [])], ["running", "queued"])


if __name__ == "__main__":
    unittest.main()
