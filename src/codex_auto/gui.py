from __future__ import annotations

import json
import queue
import threading
import traceback
from pathlib import Path
from tkinter import BOTH, END, LEFT, W, filedialog, messagebox, StringVar, Tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable

from .github_api import GitHubClient, GitHubRepository
from .models import ProjectContext, RuntimeOptions
from .orchestrator import Orchestrator
from .utils import read_json, read_jsonl


class CodexAutoGUI:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("코덱스 오토 워크스페이스")
        self.root.geometry("1500x920")
        self.root.minsize(1180, 760)

        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.repo_index: dict[str, dict[str, object]] = {}
        self.github_repo_index: dict[str, GitHubRepository] = {}
        self.current_project: ProjectContext | None = None

        self.repo_url_var = StringVar()
        self.branch_var = StringVar(value="main")
        self.workspace_root_var = StringVar(value=".codex-auto-workspace")
        self.model_var = StringVar(value="gpt-5.4")
        self.effort_var = StringVar(value="medium")
        self.approval_var = StringVar(value="never")
        self.sandbox_var = StringVar(value="workspace-write")
        self.test_cmd_var = StringVar(value="python -m pytest")
        self.max_blocks_var = StringVar(value="1")
        self.allow_push_var = StringVar(value="false")
        self.github_query_var = StringVar()
        self.github_url_mode_var = StringVar(value="ssh")

        self.status_var = StringVar(value="대기 중")
        self.repo_count_var = StringVar(value="0")
        self.ready_count_var = StringVar(value="0")
        self.active_count_var = StringVar(value="0")
        self.failed_count_var = StringVar(value="0")
        self.input_tokens_var = StringVar(value="0")
        self.cached_tokens_var = StringVar(value="0")
        self.output_tokens_var = StringVar(value="0")
        self.current_repo_var = StringVar(value="선택 없음")
        self.block_progress_var = StringVar(value="0 / 0")
        self.loop_status_var = StringVar(value="대기")
        self.checkpoint_status_var = StringVar(value="없음")
        self.next_action_var = StringVar(value="저장소를 선택한 뒤 실행")
        self.timeline_caption_var = StringVar(value="준비")

        self._configure_style()
        self._build_layout()
        self._schedule_queue_poll()
        self.refresh_repositories()

    def _configure_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("App.TFrame", background="#f4efe7")
        style.configure("Card.TLabelframe", background="#fffaf3", borderwidth=1)
        style.configure("Card.TLabelframe.Label", background="#fffaf3", foreground="#42372b", font=("Malgun Gothic", 10, "bold"))
        style.configure("Hero.TLabel", background="#25443d", foreground="#fff9ef", font=("Malgun Gothic", 20, "bold"))
        style.configure("HeroSub.TLabel", background="#25443d", foreground="#ddd4c7", font=("Malgun Gothic", 10))
        style.configure("ProgressCard.TFrame", background="#fffaf3")
        style.configure("ProgressTitle.TLabel", background="#fffaf3", foreground="#6b5b4d", font=("Malgun Gothic", 10, "bold"))
        style.configure("ProgressValue.TLabel", background="#fffaf3", foreground="#1f2937", font=("Malgun Gothic", 18, "bold"))
        style.configure("Timeline.TLabel", background="#fffaf3", foreground="#4b5563", font=("Malgun Gothic", 10))

    def _build_layout(self) -> None:
        root_frame = ttk.Frame(self.root, padding=14, style="App.TFrame")
        root_frame.pack(fill=BOTH, expand=True)

        hero = ttk.Frame(root_frame, style="App.TFrame")
        hero.pack(fill="x")
        ttk.Label(hero, text="코덱스 오토", style="Hero.TLabel", anchor="w", padding=(18, 18, 18, 6)).pack(fill="x")
        ttk.Label(
            hero,
            text="GitHub 저장소를 SSH 기준으로 선택하고, Codex 개선 루프를 안전하게 실행합니다.",
            style="HeroSub.TLabel",
            anchor="w",
            padding=(18, 0, 18, 18),
        ).pack(fill="x")

        self._build_stats(root_frame)

        content = ttk.Panedwindow(root_frame, orient="horizontal")
        content.pack(fill=BOTH, expand=True, pady=(12, 0))
        left = ttk.Frame(content, style="App.TFrame")
        right = ttk.Frame(content, style="App.TFrame")
        content.add(left, weight=38)
        content.add(right, weight=62)

        self._build_left(left)
        self._build_right(right)

    def _build_stats(self, parent: ttk.Frame) -> None:
        row = ttk.Frame(parent, style="App.TFrame")
        row.pack(fill="x", pady=(10, 0))
        for title, variable in [
            ("관리 저장소", self.repo_count_var),
            ("준비 완료", self.ready_count_var),
            ("실행 중", self.active_count_var),
            ("주의 필요", self.failed_count_var),
            ("입력 토큰", self.input_tokens_var),
            ("캐시 입력", self.cached_tokens_var),
            ("출력 토큰", self.output_tokens_var),
        ]:
            card = ttk.LabelFrame(row, text=title, padding=10, style="Card.TLabelframe")
            card.pack(side=LEFT, fill="x", expand=True, padx=(0, 10))
            ttk.Label(card, textvariable=variable, font=("Malgun Gothic", 16, "bold")).pack(anchor=W)

    def _build_left(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=BOTH, expand=True)

        managed_tab = ttk.Frame(notebook)
        github_tab = ttk.Frame(notebook)
        notebook.add(managed_tab, text="관리 중 저장소")
        notebook.add(github_tab, text="GitHub 검색")

        self._build_managed_repo_panel(managed_tab)
        self._build_github_panel(github_tab)

    def _build_managed_repo_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="관리 중 저장소", padding=12, style="Card.TLabelframe")
        frame.pack(fill=BOTH, expand=True)

        tools = ttk.Frame(frame)
        tools.pack(fill="x", pady=(0, 10))
        ttk.Button(tools, text="새로고침", command=self.refresh_repositories).pack(side=LEFT)
        ttk.Button(tools, text="선택 불러오기", command=self.load_selected_repository).pack(side=LEFT, padx=(8, 0))

        columns = ("slug", "branch", "status", "safe_revision", "last_run")
        self.repo_tree = ttk.Treeview(frame, columns=columns, show="headings", height=20)
        for key, title, width in [
            ("slug", "슬러그", 230),
            ("branch", "브랜치", 80),
            ("status", "상태", 120),
            ("safe_revision", "안전 리비전", 110),
            ("last_run", "마지막 실행", 160),
        ]:
            self.repo_tree.heading(key, text=title)
            self.repo_tree.column(key, width=width, anchor=W)
        self.repo_tree.pack(fill=BOTH, expand=True)
        self.repo_tree.bind("<<TreeviewSelect>>", self._on_repo_selected)

    def _build_github_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="GitHub 공개 저장소 검색", padding=12, style="Card.TLabelframe")
        frame.pack(fill=BOTH, expand=True)

        search_row = ttk.Frame(frame)
        search_row.pack(fill="x", pady=(0, 10))
        ttk.Label(search_row, text="검색어").pack(side=LEFT)
        ttk.Entry(search_row, textvariable=self.github_query_var, width=38).pack(side=LEFT, padx=(8, 8), fill="x", expand=True)
        ttk.Button(search_row, text="검색", command=self.search_github_repositories).pack(side=LEFT)

        mode_row = ttk.Frame(frame)
        mode_row.pack(fill="x", pady=(0, 10))
        ttk.Label(mode_row, text="적용 URL 방식").pack(side=LEFT)
        ttk.Combobox(mode_row, textvariable=self.github_url_mode_var, values=["ssh", "https"], state="readonly", width=10).pack(side=LEFT, padx=(8, 0))

        ttk.Label(
            frame,
            text="기본은 SSH clone URL 입니다. 비공개 저장소는 이 화면 대신 직접 SSH URL을 붙여넣으면 됩니다.",
        ).pack(anchor=W, pady=(0, 8))

        columns = ("full_name", "branch", "visibility", "stars")
        self.github_tree = ttk.Treeview(frame, columns=columns, show="headings", height=18)
        for key, title, width in [
            ("full_name", "저장소", 260),
            ("branch", "기본 브랜치", 100),
            ("visibility", "공개 여부", 90),
            ("stars", "Stars", 70),
        ]:
            self.github_tree.heading(key, text=title)
            self.github_tree.column(key, width=width, anchor=W)
        self.github_tree.pack(fill=BOTH, expand=True)

        ttk.Button(frame, text="선택 저장소 적용", command=self.apply_selected_github_repository).pack(anchor=W, pady=(10, 0))

    def _build_right(self, parent: ttk.Frame) -> None:
        self._build_progress_panel(parent)
        self._build_form(parent)
        self._build_output(parent)

    def _build_progress_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="진행 현황", padding=12, style="Card.TLabelframe")
        frame.pack(fill="x")

        top = ttk.Frame(frame, style="ProgressCard.TFrame")
        top.pack(fill="x")
        for title, variable in [
            ("저장소", self.current_repo_var),
            ("블록", self.block_progress_var),
            ("루프 상태", self.loop_status_var),
            ("체크포인트", self.checkpoint_status_var),
        ]:
            card = ttk.Frame(top, style="ProgressCard.TFrame")
            card.pack(side=LEFT, fill="x", expand=True, padx=(0, 10))
            ttk.Label(card, text=title, style="ProgressTitle.TLabel").pack(anchor=W)
            ttk.Label(card, textvariable=variable, style="ProgressValue.TLabel").pack(anchor=W, pady=(4, 0))

        ttk.Label(frame, text="타임라인", style="ProgressTitle.TLabel").pack(anchor=W, pady=(12, 4))
        self.timeline_progress = ttk.Progressbar(frame, mode="determinate", maximum=4)
        self.timeline_progress.pack(fill="x")
        ttk.Label(frame, text="입력 -> 초기화 -> 반복 실행 -> 체크포인트", style="Timeline.TLabel").pack(anchor=W, pady=(6, 0))
        ttk.Label(frame, textvariable=self.timeline_caption_var, style="Timeline.TLabel").pack(anchor=W, pady=(2, 0))
        ttk.Label(frame, text="다음 행동", style="ProgressTitle.TLabel").pack(anchor=W, pady=(12, 4))
        ttk.Label(frame, textvariable=self.next_action_var, style="Timeline.TLabel").pack(anchor=W)

    def _build_form(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="실행 설정", padding=12, style="Card.TLabelframe")
        frame.pack(fill="x")

        notebook = ttk.Notebook(frame)
        notebook.pack(fill="x")
        project_tab = ttk.Frame(notebook)
        execution_tab = ttk.Frame(notebook)
        plan_tab = ttk.Frame(notebook)
        checkpoint_tab = ttk.Frame(notebook)
        notebook.add(project_tab, text="프로젝트")
        notebook.add(execution_tab, text="실행")
        notebook.add(plan_tab, text="장기 계획")
        notebook.add(checkpoint_tab, text="체크포인트")

        self._build_project_tab(project_tab)
        self._build_execution_tab(execution_tab)
        self._build_plan_tab(plan_tab)
        self._build_checkpoint_tab(checkpoint_tab)

        ttk.Label(
            frame,
            text="실행 버튼 하나로 초기 설정과 블록 실행을 함께 처리합니다.",
        ).pack(anchor=W, pady=(10, 0))

        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(12, 0))
        self.action_buttons: list[ttk.Button] = []
        for label, handler in [
            ("실행", self.run_blocks),
            ("이어서 실행", self.resume_run),
            ("승인+업로드", self.approve_and_push_checkpoint),
            ("새로고침", self.refresh_repositories),
        ]:
            button = ttk.Button(actions, text=label, command=handler)
            button.pack(side=LEFT, padx=(0, 8))
            self.action_buttons.append(button)

    def _build_project_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)

        def add_row(row: int, label: str, variable: StringVar) -> None:
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky=W, padx=(0, 10), pady=6)
            ttk.Entry(parent, textvariable=variable, width=72).grid(row=row, column=1, sticky="ew", pady=6)

        add_row(0, "저장소 URL", self.repo_url_var)
        add_row(1, "브랜치", self.branch_var)
        add_row(2, "워크스페이스 루트", self.workspace_root_var)
        ttk.Button(parent, text="찾아보기", command=self._choose_workspace_root).grid(row=2, column=2, padx=(8, 0), pady=6)

    def _build_execution_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        for row, label, variable, values in [
            (0, "모델", self.model_var, ["gpt-5.4", "gpt-5"]),
            (1, "추론 강도", self.effort_var, ["low", "medium", "high", "xhigh"]),
            (2, "승인 모드", self.approval_var, ["never", "on-request", "untrusted", "on-failure"]),
            (3, "샌드박스", self.sandbox_var, ["workspace-write", "read-only", "danger-full-access"]),
            (4, "원격 push", self.allow_push_var, ["false", "true"]),
        ]:
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky=W, padx=(0, 10), pady=6)
            ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=20).grid(row=row, column=1, sticky=W, pady=6)
        ttk.Label(parent, text="최대 블록 수").grid(row=5, column=0, sticky=W, padx=(0, 10), pady=6)
        ttk.Entry(parent, textvariable=self.max_blocks_var, width=10).grid(row=5, column=1, sticky=W, pady=6)
        ttk.Label(parent, text="테스트 명령").grid(row=6, column=0, sticky=W, padx=(0, 10), pady=6)
        ttk.Entry(parent, textvariable=self.test_cmd_var, width=72).grid(row=6, column=1, sticky="ew", pady=6)

    def _build_plan_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="장기 계획 입력 하나만 사용합니다. 계획 markdown 전체를 붙여넣거나, 생성 방향만 짧게 써도 됩니다.",
        ).pack(anchor=W, pady=(0, 6))
        tools = ttk.Frame(parent)
        tools.pack(fill="x", pady=(0, 8))
        ttk.Button(tools, text="파일 불러오기", command=self._load_long_term_plan_input).pack(side=LEFT)
        ttk.Button(tools, text="입력 비우기", command=self._clear_long_term_plan_input).pack(side=LEFT, padx=(8, 0))
        self.long_term_plan_text = ScrolledText(parent, height=12, wrap="word")
        self.long_term_plan_text.pack(fill=BOTH, expand=True)
        ttk.Label(parent, text="추가 실행 지시가 필요하면 아래에 적습니다.").pack(anchor=W, pady=(10, 6))
        self.extra_prompt_text = ScrolledText(parent, height=8, wrap="word")
        self.extra_prompt_text.pack(fill=BOTH, expand=True)

    def _build_checkpoint_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="체크포인트 승인 메모").pack(anchor=W, pady=(0, 6))
        self.checkpoint_notes_text = ScrolledText(parent, height=10, wrap="word")
        self.checkpoint_notes_text.pack(fill=BOTH, expand=True)
        self.checkpoint_notes_text.insert(
            "1.0",
            "예시:\n"
            "- 장기 계획과 현재 변경이 일치함\n"
            "- 다음 체크포인트 전까지 범위를 유지할 것\n",
        )

    def _build_output(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="실행 결과", padding=12, style="Card.TLabelframe")
        frame.pack(fill=BOTH, expand=True, pady=(12, 0))

        status_row = ttk.Frame(frame)
        status_row.pack(fill="x")
        ttk.Label(status_row, text="상태").pack(side=LEFT)
        ttk.Label(status_row, textvariable=self.status_var).pack(side=LEFT, padx=(8, 0))

        tabs = ttk.Notebook(frame)
        tabs.pack(fill=BOTH, expand=True, pady=(10, 0))

        summary_tab = ttk.Frame(tabs)
        self.summary_text = ScrolledText(summary_tab, wrap="word", height=10)
        self.summary_text.pack(fill=BOTH, expand=True)
        self.summary_text.configure(state="disabled")
        tabs.add(summary_tab, text="요약")

        detail_tab = ttk.Frame(tabs)
        self.detail_text = ScrolledText(detail_tab, wrap="word", height=18)
        self.detail_text.pack(fill=BOTH, expand=True)
        self.detail_text.configure(state="disabled")
        tabs.add(detail_tab, text="상세 정보")

        log_tab = ttk.Frame(tabs)
        self.log_text = ScrolledText(log_tab, wrap="word", height=18)
        self.log_text.pack(fill=BOTH, expand=True)
        self.log_text.configure(state="disabled")
        tabs.add(log_tab, text="활동 로그")

    def _schedule_queue_poll(self) -> None:
        self.root.after(150, self._poll_queue)

    def _poll_queue(self) -> None:
        while True:
            try:
                event, payload = self.queue.get_nowait()
            except queue.Empty:
                break
            if event == "log":
                self._append_log(str(payload))
            elif event == "done":
                data = payload if isinstance(payload, dict) else {}
                self._set_busy(False, data.get("status", "대기 중"))
                if "details" in data:
                    self._set_details(str(data["details"]))
                self.refresh_repositories()
            elif event == "error":
                self._set_busy(False, "실패")
                self._append_log(str(payload))
                messagebox.showerror("코덱스 오토", str(payload))
            elif event == "github_results":
                self._populate_github_results(payload if isinstance(payload, list) else [])
        self._schedule_queue_poll()

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(END, message.rstrip() + "\n")
        self.log_text.see(END)
        self.log_text.configure(state="disabled")

    def _set_details(self, content: str) -> None:
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", END)
        self.detail_text.insert("1.0", content)
        self.detail_text.configure(state="disabled")

    def _set_summary(self, content: str) -> None:
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", END)
        self.summary_text.insert("1.0", content)
        self.summary_text.configure(state="disabled")

    def _set_busy(self, busy: bool, label: str = "대기 중") -> None:
        self.busy = busy
        self.status_var.set(label)
        for button in self.action_buttons:
            button.state(["disabled"] if busy else ["!disabled"])

    def _orchestrator(self) -> Orchestrator:
        return Orchestrator(Path(self.workspace_root_var.get().strip() or ".codex-auto-workspace"))

    def _github_client(self) -> GitHubClient:
        return GitHubClient()

    def _runtime(self) -> RuntimeOptions:
        try:
            max_blocks = max(1, int(self.max_blocks_var.get().strip() or "1"))
        except ValueError as exc:
            raise ValueError("최대 블록 수는 정수여야 합니다.") from exc
        effort = self.effort_var.get().strip().lower() or "medium"
        if effort not in {"low", "medium", "high", "xhigh"}:
            raise ValueError("추론 강도는 low, medium, high, xhigh 중 하나여야 합니다.")
        return RuntimeOptions(
            model=self.model_var.get().strip() or "gpt-5.4",
            effort=effort,
            extra_prompt=self.extra_prompt_text.get("1.0", END).strip(),
            init_plan_prompt=self.init_plan_prompt_text.get("1.0", END).strip(),
            approval_mode=self.approval_var.get().strip() or "never",
            sandbox_mode=self.sandbox_var.get().strip() or "workspace-write",
            test_cmd=self.test_cmd_var.get().strip() or "python -m pytest",
            max_blocks=max_blocks,
            allow_push=self.allow_push_var.get().strip().lower() == "true",
        )

    def _repo_inputs(self) -> tuple[str, str]:
        repo_url = self.repo_url_var.get().strip()
        branch = self.branch_var.get().strip() or "main"
        if not repo_url:
            raise ValueError("저장소 URL이 필요합니다.")
        return repo_url, branch

    def _long_term_plan_input(self) -> str:
        return self.long_term_plan_text.get("1.0", END).strip()

    def _render_result(self, result: object) -> str:
        if isinstance(result, ProjectContext):
            return json.dumps({"metadata": result.metadata.to_dict(), "loop_state": result.loop_state.to_dict()}, indent=2, ensure_ascii=False)
        if isinstance(result, (list, dict)):
            return json.dumps(result, indent=2, ensure_ascii=False)
        return str(result)

    def _run_async(self, label: str, worker: Callable[[], object]) -> None:
        if self.busy:
            messagebox.showinfo("코덱스 오토", "다른 작업이 이미 실행 중입니다.")
            return
        self._set_busy(True, f"{label} 실행 중")
        self._append_log(f"[시작] {label}")

        def target() -> None:
            try:
                result = worker()
                self.queue.put(("done", {"status": f"{label} 완료", "details": self._render_result(result)}))
                self.queue.put(("log", f"[완료] {label}"))
            except Exception as exc:
                error_text = f"{label} 실패: {exc}"
                self.queue.put(("log", f"[오류] {error_text}\n{traceback.format_exc()}"))
                self.queue.put(("error", error_text))

        threading.Thread(target=target, daemon=True).start()

    def _workspace_usage_summary(self, projects: list[ProjectContext]) -> dict[str, int]:
        usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
        for project in projects:
            for item in read_jsonl(project.paths.pass_log_file):
                item_usage = item.get("usage", {})
                for key in usage:
                    value = item_usage.get(key, 0)
                    if isinstance(value, int):
                        usage[key] += value
        return usage

    def _format_workspace_summary(self, rows: list[dict[str, object]], usage: dict[str, int]) -> str:
        lines = [
            "워크스페이스 요약",
            "",
            f"관리 저장소 수: {len(rows)}",
            f"준비 완료: {self.ready_count_var.get()}",
            f"실행 중: {self.active_count_var.get()}",
            f"주의 필요: {self.failed_count_var.get()}",
            "",
            "Codex 토큰 사용량 합계",
            f"- input_tokens: {usage['input_tokens']}",
            f"- cached_input_tokens: {usage['cached_input_tokens']}",
            f"- output_tokens: {usage['output_tokens']}",
        ]
        return "\n".join(lines)

    def _populate_github_results(self, repos: list[GitHubRepository]) -> None:
        self.github_repo_index = {}
        for item in self.github_tree.get_children():
            self.github_tree.delete(item)
        for repo in repos:
            self.github_repo_index[repo.full_name] = repo
            self.github_tree.insert("", END, iid=repo.full_name, values=repo.to_display_row())
        self._set_details(
            json.dumps(
                [
                    {
                        "full_name": repo.full_name,
                        "ssh_url": repo.ssh_url,
                        "clone_url": repo.clone_url,
                        "default_branch": repo.default_branch,
                        "description": repo.description,
                    }
                    for repo in repos
                ],
                indent=2,
                ensure_ascii=False,
            )
        )

    def refresh_repositories(self) -> None:
        try:
            projects = self._orchestrator().list_projects()
        except Exception as exc:
            self._append_log(f"[경고] 목록 조회 실패: {exc}")
            return

        self.repo_index = {}
        for item in self.repo_tree.get_children():
            self.repo_tree.delete(item)

        rows: list[dict[str, object]] = []
        ready = 0
        active = 0
        failed = 0
        for project in projects:
            status = project.metadata.current_status
            if status == "ready":
                ready += 1
            elif status.startswith("running:"):
                active += 1
            elif status.endswith("failed") or "rollback" in status:
                failed += 1
            row = {
                "repo_id": project.metadata.repo_id,
                "slug": project.metadata.slug,
                "repo_url": project.metadata.repo_url,
                "branch": project.metadata.branch,
                "status": status,
                "last_run_at": project.metadata.last_run_at,
                "safe_revision": (project.metadata.current_safe_revision or "")[:10],
            }
            self.repo_index[project.metadata.repo_id] = row
            self.repo_tree.insert("", END, iid=project.metadata.repo_id, values=(row["slug"], row["branch"], row["status"], row["safe_revision"], row["last_run_at"] or ""))
            rows.append(row)

        usage = self._workspace_usage_summary(projects)
        self.repo_count_var.set(str(len(rows)))
        self.ready_count_var.set(str(ready))
        self.active_count_var.set(str(active))
        self.failed_count_var.set(str(failed))
        self.input_tokens_var.set(f"{usage['input_tokens']:,}")
        self.cached_tokens_var.set(f"{usage['cached_input_tokens']:,}")
        self.output_tokens_var.set(f"{usage['output_tokens']:,}")
        self._set_summary(self._format_workspace_summary(rows, usage))
        self._set_details(json.dumps(rows, indent=2, ensure_ascii=False))

    def load_selected_repository(self, show_message: bool = True) -> None:
        selected = self.repo_tree.selection()
        if not selected:
            if show_message:
                messagebox.showinfo("코덱스 오토", "관리 중인 저장소를 먼저 선택하세요.")
            return
        row = self.repo_index.get(selected[0])
        if not row:
            return
        self.repo_url_var.set(str(row["repo_url"]))
        self.branch_var.set(str(row["branch"]))
        if show_message:
            self._append_log(f"[정보] {row['slug']} 불러옴")

    def _on_repo_selected(self, _event: object) -> None:
        self.load_selected_repository(show_message=False)

    def search_github_repositories(self) -> None:
        query = self.github_query_var.get().strip()
        if not query:
            messagebox.showerror("코덱스 오토", "GitHub 검색어를 입력하세요.")
            return
        client = self._github_client()

        def worker() -> dict[str, object]:
            repos = client.search_repositories(query)
            self.queue.put(("github_results", repos))
            return {"검색 결과 수": len(repos)}

        self._run_async("GitHub 검색", worker)

    def apply_selected_github_repository(self) -> None:
        selected = self.github_tree.selection()
        if not selected:
            messagebox.showinfo("코덱스 오토", "GitHub 저장소를 먼저 선택하세요.")
            return
        repo = self.github_repo_index.get(selected[0])
        if not repo:
            return
        mode = self.github_url_mode_var.get().strip().lower()
        url = repo.ssh_url if mode == "ssh" else repo.clone_url
        self.repo_url_var.set(url or repo.html_url)
        self.branch_var.set(repo.default_branch or "main")
        self._append_log(f"[정보] GitHub 저장소 적용: {repo.full_name} ({mode})")

    def _choose_workspace_root(self) -> None:
        chosen = filedialog.askdirectory(initialdir=str(Path.cwd()))
        if chosen:
            self.workspace_root_var.set(chosen)
            self.refresh_repositories()

    def _load_long_term_plan_input(self) -> None:
        chosen = filedialog.askopenfilename(title="LONG_TERM_PLAN.md 선택", filetypes=[("Markdown", "*.md"), ("All files", "*.*")])
        if chosen:
            content = Path(chosen).read_text(encoding="utf-8")
            self.long_term_plan_text.delete("1.0", END)
            self.long_term_plan_text.insert("1.0", content)

    def _clear_long_term_plan_input(self) -> None:
        self.long_term_plan_text.delete("1.0", END)

    def run_blocks(self) -> None:
        try:
            repo_url, branch = self._repo_inputs()
            runtime = self._runtime()
            long_term_input = self._long_term_plan_input()
            orchestrator = self._orchestrator()
        except Exception as exc:
            messagebox.showerror("코덱스 오토", str(exc))
            return
        self._run_async(
            "실행",
            lambda: orchestrator.run(
                repo_url=repo_url,
                branch=branch,
                runtime=runtime,
                long_term_plan_input=long_term_input,
                resume=False,
            ),
        )

    def resume_run(self) -> None:
        try:
            repo_url, branch = self._repo_inputs()
            runtime = self._runtime()
            orchestrator = self._orchestrator()
        except Exception as exc:
            messagebox.showerror("코덱스 오토", str(exc))
            return
        self._run_async("이어서 실행", lambda: orchestrator.resume(repo_url=repo_url, branch=branch, runtime=runtime))

    def approve_and_push_checkpoint(self) -> None:
        try:
            repo_url, branch = self._repo_inputs()
            orchestrator = self._orchestrator()
            notes = self.checkpoint_notes_text.get("1.0", END).strip()
        except Exception as exc:
            messagebox.showerror("코덱스 오토", str(exc))
            return
        self._run_async(
            "체크포인트 승인+업로드",
            lambda: orchestrator.approve_checkpoint(
                repo_url=repo_url,
                branch=branch,
                review_notes=notes,
                push=True,
            ),
        )


def main() -> int:
    root = Tk()
    app = CodexAutoGUI(root)
    app._append_log("GUI 준비 완료")
    root.mainloop()
    return 0
