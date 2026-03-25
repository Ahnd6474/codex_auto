from __future__ import annotations

import json
import queue
import threading
import traceback
from pathlib import Path
from tkinter import BOTH, END, LEFT, W, Canvas, filedialog, messagebox, StringVar, Tk
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
        self.current_plan_steps: list[dict[str, object]] = []
        self.left_panel_visible = True

        self.repo_url_var = StringVar()
        self.branch_var = StringVar(value="main")
        self.workspace_root_var = StringVar(value=".codex-auto-workspace")
        self.model_var = StringVar(value="gpt-5.4")
        self.effort_var = StringVar(value="medium")
        self.approval_var = StringVar(value="never")
        self.sandbox_var = StringVar(value="workspace-write")
        self.test_cmd_var = StringVar(value="python -m pytest")
        self.max_blocks_var = StringVar(value="1")
        self.allow_push_var = StringVar(value="true")
        self.github_query_var = StringVar()
        self.github_url_mode_var = StringVar(value="ssh")
        self.model_choices = ["gpt-5.4", "gpt-5"]

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
        self.codex_status_var = StringVar(value="대기")
        self.checkpoint_status_var = StringVar(value="없음")
        self.timeline_caption_var = StringVar(value="준비")
        self.stop_button: ttk.Button | None = None

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
        self.content_pane = content
        left = ttk.Frame(content, style="App.TFrame")
        right = ttk.Frame(content, style="App.TFrame")
        self.left_panel = left
        self.right_panel = right
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
        ttk.Button(tools, text="패널 접기", command=self.toggle_left_panel).pack(side=LEFT, padx=(8, 0))

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
        ttk.Entry(search_row, textvariable=self.github_query_var, width=24).pack(side=LEFT, padx=(8, 8), fill="x", expand=True)
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
        content = ttk.Panedwindow(parent, orient="vertical")
        content.pack(fill=BOTH, expand=True)
        top = ttk.Frame(content, style="App.TFrame")
        bottom = ttk.Frame(content, style="App.TFrame")
        content.add(top, weight=42)
        content.add(bottom, weight=58)
        self._build_right_top(top)
        self._build_output(bottom)

    def _build_right_top(self, parent: ttk.Frame) -> None:
        outer = ttk.Frame(parent, style="App.TFrame")
        outer.pack(fill=BOTH, expand=True)
        canvas = Canvas(outer, bg="#f4efe7", highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=LEFT, fill="y")
        canvas.pack(side=LEFT, fill=BOTH, expand=True)

        content = ttk.Frame(canvas, style="App.TFrame")
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def on_configure(_event: object) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(event: object) -> None:
            width = getattr(event, "width", 0)
            if width:
                canvas.itemconfigure(window_id, width=width)

        content.bind("<Configure>", on_configure)
        canvas.bind("<Configure>", on_canvas_configure)

        self._build_progress_panel(content)
        self._build_form(content)

    def _build_progress_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="진행 현황", padding=12, style="Card.TLabelframe")
        frame.pack(fill="x")

        actions = ttk.Frame(frame, style="ProgressCard.TFrame")
        actions.pack(fill="x", pady=(0, 12))
        self.action_buttons = []
        for label, handler in [
            ("실행", self.run_blocks),
            ("중지", self.stop_run),
            ("새로고침", self.refresh_repositories),
        ]:
            button = ttk.Button(actions, text=label, command=handler)
            button.pack(side=LEFT, padx=(0, 8))
            self.action_buttons.append(button)
            if label == "중지":
                self.stop_button = button
        ttk.Button(actions, text="저장소 접기", command=self.toggle_left_panel).pack(side=LEFT, padx=(0, 8))
        ttk.Button(actions, text="종료", command=self.root.destroy).pack(side=LEFT, padx=(0, 8))

        runtime_row = ttk.Frame(frame, style="ProgressCard.TFrame")
        runtime_row.pack(fill="x", pady=(0, 12))
        ttk.Label(runtime_row, text="모델", style="ProgressTitle.TLabel").pack(side=LEFT)
        ttk.Combobox(runtime_row, textvariable=self.model_var, values=self.model_choices, width=18).pack(side=LEFT, padx=(8, 12))
        ttk.Label(runtime_row, text="추론 강도", style="ProgressTitle.TLabel").pack(side=LEFT)
        ttk.Combobox(
            runtime_row,
            textvariable=self.effort_var,
            values=["low", "medium", "high", "xhigh"],
            state="readonly",
            width=10,
        ).pack(side=LEFT, padx=(8, 12))
        ttk.Label(runtime_row, text="모델 직접 입력 가능", style="Timeline.TLabel").pack(side=LEFT)

        top_row = ttk.Frame(frame, style="ProgressCard.TFrame")
        top_row.pack(fill="x")
        bottom_row = ttk.Frame(frame, style="ProgressCard.TFrame")
        bottom_row.pack(fill="x", pady=(8, 0))
        cards = [
            ("저장소", self.current_repo_var),
            ("블록", self.block_progress_var),
            ("Codex", self.codex_status_var),
            ("루프 상태", self.loop_status_var),
            ("체크포인트", self.checkpoint_status_var),
        ]
        for index, (title, variable) in enumerate(cards):
            row = top_row if index < 3 else bottom_row
            card = ttk.Frame(row, style="ProgressCard.TFrame")
            card.pack(side=LEFT, fill="x", expand=True, padx=(0, 10))
            ttk.Label(card, text=title, style="ProgressTitle.TLabel").pack(anchor=W)
            ttk.Label(card, textvariable=variable, style="ProgressValue.TLabel").pack(anchor=W, pady=(4, 0))

        controls = ttk.Frame(frame, style="ProgressCard.TFrame")
        controls.pack(fill="x", pady=(12, 4))
        ttk.Label(controls, text="타임라인 / 일 배분", style="ProgressTitle.TLabel").pack(side=LEFT)
        ttk.Button(controls, text="Codex 배분", command=self.plan_work_distribution).pack(side=LEFT, padx=(12, 0))

        self.timeline_progress = ttk.Progressbar(frame, mode="determinate", maximum=4)
        self.timeline_progress.pack(fill="x")
        ttk.Label(frame, textvariable=self.timeline_caption_var, style="Timeline.TLabel").pack(anchor=W, pady=(6, 0))
        ttk.Label(frame, text="검증: 각 pass 후 test, 실패 시 rollback", style="Timeline.TLabel").pack(anchor=W, pady=(6, 0))
        ttk.Label(frame, text="동기화: 블록 완료 후 GitHub 자동 push", style="Timeline.TLabel").pack(anchor=W, pady=(2, 0))
        canvas_wrap = ttk.Frame(frame)
        canvas_wrap.pack(fill="x", pady=(10, 0))
        self.plan_canvas = Canvas(canvas_wrap, height=150, bg="#fffaf3", highlightthickness=0)
        h_scroll = ttk.Scrollbar(canvas_wrap, orient="horizontal", command=self.plan_canvas.xview)
        v_scroll = ttk.Scrollbar(canvas_wrap, orient="vertical", command=self.plan_canvas.yview)
        self.plan_canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        self.plan_canvas.pack(side=LEFT, fill="x", expand=True)
        v_scroll.pack(side=LEFT, fill="y")
        h_scroll.pack(fill="x")
        ttk.Label(frame, text="일 배분 편집", style="ProgressTitle.TLabel").pack(anchor=W, pady=(10, 4))
        self.work_items_text = ScrolledText(frame, height=4, wrap="word")
        self.work_items_text.pack(fill="x")
        self.work_items_text.bind("<<Modified>>", self._on_work_items_modified)

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
            (0, "모델", self.model_var, self.model_choices),
            (1, "추론 강도", self.effort_var, ["low", "medium", "high", "xhigh"]),
            (2, "승인 모드", self.approval_var, ["never", "on-request", "untrusted", "on-failure"]),
        ]:
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky=W, padx=(0, 10), pady=6)
            state = "readonly" if label != "모델" else "normal"
            ttk.Combobox(parent, textvariable=variable, values=values, state=state, width=20).grid(row=row, column=1, sticky=W, pady=6)
        ttk.Label(parent, text="모델은 직접 입력, 강도는 선택").grid(row=3, column=1, sticky=W, pady=(0, 6))
        ttk.Label(parent, text="권한 범위").grid(row=4, column=0, sticky=W, padx=(0, 10), pady=6)
        ttk.Label(parent, text="managed workspace only").grid(row=4, column=1, sticky=W, pady=6)
        ttk.Label(parent, text="GitHub 동기화").grid(row=5, column=0, sticky=W, padx=(0, 10), pady=6)
        ttk.Label(parent, text="각 블록 완료 후 자동 push").grid(row=5, column=1, sticky=W, pady=6)
        ttk.Label(parent, text="최대 블록 수").grid(row=6, column=0, sticky=W, padx=(0, 10), pady=6)
        ttk.Entry(parent, textvariable=self.max_blocks_var, width=10).grid(row=6, column=1, sticky=W, pady=6)
        ttk.Label(parent, text="테스트 명령").grid(row=7, column=0, sticky=W, padx=(0, 10), pady=6)
        ttk.Entry(parent, textvariable=self.test_cmd_var, width=72).grid(row=7, column=1, sticky="ew", pady=6)

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
        ttk.Button(parent, text="승인+업로드", command=self.approve_and_push_checkpoint).pack(anchor=W, pady=(0, 8))
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
            elif event == "plan_distribution":
                self._render_work_distribution(payload if isinstance(payload, dict) else None)
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
        if self.stop_button is not None:
            self.stop_button.state(["!disabled"] if busy else ["disabled"])
        if busy:
            self.loop_status_var.set(label)
            self.codex_status_var.set("실행 중")
        else:
            self.codex_status_var.set("대기")

    def _set_progress_from_context(self, context: ProjectContext | None) -> None:
        self.current_project = context
        if context is None:
            self.current_repo_var.set("선택 없음")
            self.block_progress_var.set("0 / 0")
            self.loop_status_var.set("대기")
            self.codex_status_var.set("대기")
            self.checkpoint_status_var.set("없음")
            self.timeline_caption_var.set("준비")
            self.timeline_progress.configure(value=0)
            return

        max_blocks = max(1, context.runtime.max_blocks)
        current_block = min(context.loop_state.block_index, max_blocks)
        self.current_repo_var.set(context.metadata.slug)
        self.block_progress_var.set(f"{current_block} / {max_blocks}")
        self.codex_status_var.set(self._codex_status(context))
        self.loop_status_var.set(self._human_status(context))
        self.checkpoint_status_var.set(self._checkpoint_summary(context))
        timeline_value, caption = self._timeline_state(context)
        self.timeline_progress.configure(value=timeline_value)
        self.timeline_caption_var.set(caption)

    def _codex_status(self, context: ProjectContext) -> str:
        if self.busy or context.metadata.current_status.startswith("running:"):
            return "실행 중"
        if context.loop_state.stop_requested:
            return "중지 대기"
        if context.metadata.current_status == "init_failed":
            return "오류"
        if context.loop_state.pending_checkpoint_approval:
            return "대기 중"
        return "유휴"

    def _human_status(self, context: ProjectContext) -> str:
        status = context.metadata.current_status
        if status == "ready":
            return "준비 완료"
        if status == "init_failed":
            return "초기화 실패"
        if context.loop_state.stop_requested:
            return "중지 요청됨"
        if status == "awaiting_checkpoint_approval":
            return "체크포인트 승인 대기"
        if status.startswith("running:block:"):
            block = status.rsplit(":", 1)[-1]
            return f"블록 {block} 실행 중"
        if context.loop_state.stop_reason:
            return context.loop_state.stop_reason
        return status or "대기"

    def _checkpoint_summary(self, context: ProjectContext) -> str:
        data = read_json(context.paths.checkpoint_state_file, default={"checkpoints": []})
        checkpoints = data.get("checkpoints", [])
        if not checkpoints:
            return "없음"
        approved = sum(1 for item in checkpoints if item.get("status") == "approved")
        total = len(checkpoints)
        waiting = next((item for item in checkpoints if item.get("status") == "awaiting_review"), None)
        if waiting:
            return f"{waiting.get('checkpoint_id', 'CP')} 승인 대기"
        return f"{approved} / {total} 승인"

    def _timeline_state(self, context: ProjectContext) -> tuple[int, str]:
        if context.metadata.current_status == "init_failed":
            return 1, "초기화 단계에서 멈춤"
        if context.loop_state.pending_checkpoint_approval:
            return 4, "체크포인트 검토 필요"
        if context.metadata.current_status.startswith("running:"):
            return 3, f"반복 실행 중 · block {context.loop_state.block_index}"
        if context.loop_state.block_index > 0:
            return 3, f"반복 실행 완료 · block {context.loop_state.block_index}"
        if context.metadata.current_safe_revision:
            return 2, "초기화 완료"
        return 1, "입력 확인 중"

    def _render_work_distribution(self, payload: dict[str, object] | None) -> None:
        self.work_items_text.delete("1.0", END)
        if not payload:
            self._sync_work_items_to_plan_preview()
            return

        steps = payload.get("steps", [])
        if not isinstance(steps, list) or not steps:
            self._sync_work_items_to_plan_preview()
            return

        for index, step in enumerate(steps):
            self.work_items_text.insert("end", f"{step.get('title')}\n")
        self.work_items_text.edit_modified(False)
        self._sync_work_items_to_plan_preview()

    def _read_work_items(self) -> list[str]:
        return [line.strip() for line in self.work_items_text.get("1.0", END).splitlines() if line.strip()]

    def _on_work_items_modified(self, _event: object) -> None:
        if not self.work_items_text.edit_modified():
            return
        self.work_items_text.edit_modified(False)
        self._sync_work_items_to_plan_preview()

    def _sync_work_items_to_plan_preview(self) -> None:
        items = self._read_work_items()
        if items:
            self.max_blocks_var.set(str(len(items)))
            current_index = self.current_project.loop_state.block_index if self.current_project else 0
            payload = {
                "steps": [
                    {
                        "label": f"일{chr(64 + index)}",
                        "title": item,
                        "state": "done" if index <= current_index else "current" if index == current_index + 1 else "pending",
                    }
                    for index, item in enumerate(items, start=1)
                ]
            }
            self._draw_plan_steps(payload)
            return
        self._draw_plan_steps(None)

    def _draw_plan_steps(self, payload: dict[str, object] | None) -> None:
        self.plan_canvas.delete("all")
        if not payload:
            self.plan_canvas.create_text(
                24,
                24,
                text="자동 배분을 누르거나 아래에 작업을 한 줄씩 입력하세요.",
                anchor="w",
                fill="#64748B",
                font=("Malgun Gothic", 10),
            )
            self.plan_canvas.configure(scrollregion=(0, 0, 900, 150))
            return

        steps = payload.get("steps", [])
        if not isinstance(steps, list) or not steps:
            self.plan_canvas.configure(scrollregion=(0, 0, 900, 150))
            return

        viewport_width = max(self.plan_canvas.winfo_width(), 700)
        gap_x = 16
        gap_y = 18
        arrow_width = 150
        height = 54
        start_x = 24
        start_y = 20
        row_capacity = max(1, min(4, int((viewport_width - start_x * 2 + gap_x) / (arrow_width + gap_x))))
        total_rows = (len(steps) + row_capacity - 1) // row_capacity
        canvas_height = max(120, total_rows * (height + gap_y) + 34)
        content_width = max(viewport_width, start_x * 2 + min(len(steps), row_capacity) * arrow_width + max(0, min(len(steps), row_capacity) - 1) * gap_x + 30)
        self.plan_canvas.configure(height=canvas_height, scrollregion=(0, 0, content_width, canvas_height))
        colors = {"done": "#2CB67D", "current": "#2563EB", "pending": "#CBD5E1"}
        text_colors = {"done": "white", "current": "white", "pending": "#1F2937"}
        for index, step in enumerate(steps):
            row = index // row_capacity
            col = index % row_capacity
            x = start_x + col * (arrow_width + gap_x)
            y = start_y + row * (height + gap_y)
            state = str(step.get("state", "pending"))
            fill = colors.get(state, "#CBD5E1")
            text_fill = text_colors.get(state, "#1F2937")
            points = [
                x, y,
                x + arrow_width - 26, y,
                x + arrow_width, y + height / 2,
                x + arrow_width - 26, y + height,
                x, y + height,
                x + 18, y + height / 2,
            ]
            self.plan_canvas.create_polygon(points, fill=fill, outline="")
            progress_text = "완료" if state == "done" else "진행 중" if state == "current" else "대기"
            self.plan_canvas.create_text(
                x + arrow_width / 2 - 6,
                y - 10,
                text=progress_text,
                fill="#475569",
                font=("Malgun Gothic", 9, "bold"),
            )
            self.plan_canvas.create_text(
                x + arrow_width / 2 - 6,
                y + 17,
                text=str(step.get("label", f"일{index+1}")),
                fill=text_fill,
                font=("Malgun Gothic", 12, "bold"),
            )
            self.plan_canvas.create_text(
                x + arrow_width / 2 - 6,
                y + 36,
                text=str(step.get("title", ""))[:24],
                fill=text_fill,
                font=("Malgun Gothic", 9),
            )
            if col < row_capacity - 1 and index + 1 < len(steps) and (index + 1) // row_capacity == row:
                self.plan_canvas.create_line(
                    x + arrow_width + 2,
                    y + height / 2,
                    x + arrow_width + gap_x - 2,
                    y + height / 2,
                    fill="#94A3B8",
                    width=3,
                    arrow="last",
                )

    def toggle_left_panel(self) -> None:
        if self.left_panel_visible:
            self.content_pane.forget(self.left_panel)
            self.left_panel_visible = False
            return
        self.content_pane.insert(0, self.left_panel, weight=38)
        self.left_panel_visible = True

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
            init_plan_prompt="",
            approval_mode=self.approval_var.get().strip() or "never",
            sandbox_mode="workspace-write",
            test_cmd=self.test_cmd_var.get().strip() or "python -m pytest",
            max_blocks=max_blocks,
            allow_push=True,
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
        self._set_progress_from_context(self._current_project_from_selection(projects))

    def _current_project_from_selection(self, projects: list[ProjectContext]) -> ProjectContext | None:
        selected = self.repo_tree.selection()
        if selected:
            selected_id = selected[0]
            for project in projects:
                if project.metadata.repo_id == selected_id:
                    return project
        if self.current_project is not None:
            for project in projects:
                if project.metadata.repo_id == self.current_project.metadata.repo_id:
                    return project
        repo_url = self.repo_url_var.get().strip()
        branch = self.branch_var.get().strip() or "main"
        if repo_url:
            for project in projects:
                if project.metadata.repo_url == repo_url and project.metadata.branch == branch:
                    return project
        return None

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
        self.current_project = self._orchestrator().find_project(str(row["repo_url"]), str(row["branch"]))
        self._set_progress_from_context(self.current_project)
        self._render_work_distribution(None)
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

    def plan_work_distribution(self) -> None:
        try:
            repo_url, branch = self._repo_inputs()
            runtime = self._runtime()
            long_term_input = self._long_term_plan_input()
            orchestrator = self._orchestrator()
        except Exception as exc:
            messagebox.showerror("코덱스 오토", str(exc))
            return

        def worker() -> dict[str, object]:
            result = orchestrator.plan_work(
                repo_url=repo_url,
                branch=branch,
                runtime=runtime,
                long_term_plan_input=long_term_input,
            )
            self.queue.put(("plan_distribution", result))
            return result

        self._run_async("일 배분", worker)

    def run_blocks(self) -> None:
        try:
            repo_url, branch = self._repo_inputs()
            runtime = self._runtime()
            long_term_input = self._long_term_plan_input()
            work_items = self._read_work_items()
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
                work_items=work_items,
                resume=False,
            ),
        )

    def stop_run(self) -> None:
        try:
            repo_url, branch = self._repo_inputs()
            orchestrator = self._orchestrator()
        except Exception as exc:
            messagebox.showerror("코덱스 오토", str(exc))
            return
        result = orchestrator.request_stop(repo_url=repo_url, branch=branch)
        self._append_log(f"[정보] 중지 요청: {result['status']}")
        self.refresh_repositories()

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
