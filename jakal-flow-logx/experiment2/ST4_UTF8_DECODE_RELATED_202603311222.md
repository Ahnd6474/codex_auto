# utf-8 decode error 관련 원본 로그 (요약 추출)

시간(UTC): 2026-03-31 12:22:33~12:22:48

## job_scheduler_events.jsonl

207-{"details": {}, "event_type": "job-started", "job": {"allow_background_queue": true, "chat_mode": "", "command": "generate-plan", "completed_at": null, "created_at": "2026-03-31T11:13:07+00:00", "display_name": "experiment2", "error": null, "id": "job-generate-plan-1774955587631-1", "job_lane": "execution", "project_dir": "c:\\users\\alber\\github\\experiment2", "queue_position": 0, "queue_priority": 0, "repo_id": "", "result": null, "started_at": "2026-03-31T11:13:07+00:00", "status": "running", "updated_at_ms": 1774955587631, "workspace_root": "C:\\Users\\alber\\.jakal-flow-workspace"}, "timestamp": "2026-03-31T11:13:07+00:00"}
208-{"details": {}, "event_type": "job-failed", "job": {"allow_background_queue": true, "chat_mode": "", "command": "generate-plan", "completed_at": "2026-03-31T11:16:06+00:00", "created_at": "2026-03-31T11:13:07+00:00", "display_name": "experiment2", "error": "ST4 (block B1) must depend on at least two prior steps to act as a join node.", "id": "job-generate-plan-1774955587631-1", "job_lane": "execution", "project_dir": "c:\\users\\alber\\github\\experiment2", "queue_position": 0, "queue_priority": 0, "repo_id": "", "result": null, "started_at": "2026-03-31T11:13:07+00:00", "status": "failed", "updated_at_ms": 1774955766409, "workspace_root": "C:\\Users\\alber\\.jakal-flow-workspace"}, "timestamp": "2026-03-31T11:16:06+00:00"}
209:{"details": {}, "event_type": "job-started", "job": {"allow_background_queue": true, "chat_mode": "", "command": "generate-plan", "completed_at": null, "created_at": "2026-03-31T12:22:33+00:00", "display_name": "experiment2", "error": null, "id": "job-generate-plan-1774959753056-1", "job_lane": "execution", "project_dir": "c:\\users\\alber\\github\\experiment2", "queue_position": 0, "queue_priority": 0, "repo_id": "", "result": null, "started_at": "2026-03-31T12:22:33+00:00", "status": "running", "updated_at_ms": 1774959753056, "workspace_root": "C:\\Users\\alber\\.jakal-flow-workspace"}, "timestamp": "2026-03-31T12:22:33+00:00"}
210:{"details": {}, "event_type": "job-failed", "job": {"allow_background_queue": true, "chat_mode": "", "command": "generate-plan", "completed_at": "2026-03-31T12:22:48+00:00", "created_at": "2026-03-31T12:22:33+00:00", "display_name": "experiment2", "error": "'utf-8' codec can't decode byte 0xa4 in position 5847114: invalid start byte", "id": "job-generate-plan-1774959753056-1", "job_lane": "execution", "project_dir": "c:\\users\\alber\\github\\experiment2", "queue_position": 0, "queue_priority": 0, "repo_id": "", "result": null, "started_at": "2026-03-31T12:22:33+00:00", "status": "failed", "updated_at_ms": 1774959768146, "workspace_root": "C:\\Users\\alber\\.jakal-flow-workspace"}, "timestamp": "2026-03-31T12:22:48+00:00"}

## ui-bridge_generate-plan.crash.log

8-repo_dir: C:\Users\alber\GitHub\experiment2
9-branch: main
10:exception_type: UnicodeDecodeError
11:exception_message: 'utf-8' codec can't decode byte 0xa4 in position 5847114: invalid start byte
12-
13-## Payload
--
82-}
83-
84:## Traceback
85:Traceback (most recent call last):
86-  File "\\?\C:\Users\alber\GitHub\codex_auto\src\jakal_flow\ui_bridge.py", line 728, in run_command
87-    result = handler(
--
112-           ^^^^^^^^
113-  File "<frozen codecs>", line 322, in decode
114:UnicodeDecodeError: 'utf-8' codec can't decode byte 0xa4 in position 5847114: invalid start byte

## bridge-server_generate-plan.crash.log

4-command: generate-plan
5-workspace_root: C:\Users\alber\.jakal-flow-workspace
6:exception_type: UnicodeDecodeError
7:exception_message: 'utf-8' codec can't decode byte 0xa4 in position 5847114: invalid start byte
8-
9-## Payload
--
13-}
14-
15:## Traceback
16:Traceback (most recent call last):
17-  File "\\?\C:\Users\alber\GitHub\codex_auto\src\jakal_flow\bridge_server.py", line 616, in _run_job
18-    result = run_command(command, workspace_root, payload)
--
46-           ^^^^^^^^
47-  File "<frozen codecs>", line 322, in decode
48:UnicodeDecodeError: 'utf-8' codec can't decode byte 0xa4 in position 5847114: invalid start byte
