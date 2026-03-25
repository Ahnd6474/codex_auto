from __future__ import annotations

from copy import deepcopy
import json
import queue
import textwrap
import threading
import traceback
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, W, X, Y, Canvas, StringVar, Tk, filedialog, messagebox
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from .models import ExecutionPlanState, ExecutionStep, ProjectContext, RuntimeOptions
from .orchestrator import Orchestrator
from .utils import read_jsonl_tail


def _plan_state_with_running_step(plan_state: ExecutionPlanState, step_id: str) -> ExecutionPlanState:
    updated_steps: list[ExecutionStep] = []
    for step in plan_state.steps:
        status = step.status
        if step.step_id == step_id and step.status != "completed":
            status = "running"
        elif step.status == "running":
            status = "paused"
        updated_steps.append(
            ExecutionStep(
                step_id=step.step_id,
                title=step.title,
                display_description=step.display_description,
                codex_description=step.codex_description,
                test_command=step.test_command,
                success_criteria=step.success_criteria,
                status=status,
                started_at=step.started_at,
                completed_at=step.completed_at,
                commit_hash=step.commit_hash,
                notes=step.notes,
            )
        )
    return ExecutionPlanState(
        plan_title=plan_state.plan_title,
        project_prompt=plan_state.project_prompt,
        summary=plan_state.summary,
        default_test_command=plan_state.default_test_command,
        last_updated_at=plan_state.last_updated_at,
        closeout_status=plan_state.closeout_status,
        closeout_started_at=plan_state.closeout_started_at,
        closeout_completed_at=plan_state.closeout_completed_at,
        closeout_commit_hash=plan_state.closeout_commit_hash,
        closeout_notes=plan_state.closeout_notes,
        steps=updated_steps,
    )


def _plan_state_with_closeout_status(plan_state: ExecutionPlanState, status: str) -> ExecutionPlanState:
    return ExecutionPlanState(
        plan_title=plan_state.plan_title,
        project_prompt=plan_state.project_prompt,
        summary=plan_state.summary,
        default_test_command=plan_state.default_test_command,
        last_updated_at=plan_state.last_updated_at,
        closeout_status=status,
        closeout_started_at=plan_state.closeout_started_at,
        closeout_completed_at=plan_state.closeout_completed_at,
        closeout_commit_hash=plan_state.closeout_commit_hash,
        closeout_notes=plan_state.closeout_notes,
        steps=[
            ExecutionStep(
                step_id=step.step_id,
                title=step.title,
                display_description=step.display_description,
                codex_description=step.codex_description,
                test_command=step.test_command,
                success_criteria=step.success_criteria,
                status=step.status,
                started_at=step.started_at,
                completed_at=step.completed_at,
                commit_hash=step.commit_hash,
                notes=step.notes,
            )
            for step in plan_state.steps
        ],
    )


class CodexAutoGUI:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("codex-auto")
        self.root.geometry("1560x980")
        self.root.minsize(1280, 840)

        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.stop_after_step_event = threading.Event()

        self.workspace_root_var = StringVar(value=".codex-auto-workspace")
        self.project_dir_var = StringVar()
        self.branch_var = StringVar(value="main")
        self.origin_url_var = StringVar()
        self.model_var = StringVar(value="gpt-5.4")
        self.effort_var = StringVar(value="medium")
        self.test_cmd_var = StringVar(value="python -m pytest")
        self.max_steps_var = StringVar(value="5")
        self.status_var = StringVar(value="Ready")
        self.stage_title_var = StringVar(value="Stage 1. Environment Setup")
        self.current_project_label_var = StringVar(value="No project selected")
        self.current_step_label_var = StringVar(value="No plan loaded")
        self.selected_step_id_var = StringVar(value="")
        self.selected_step_status_var = StringVar(value="")

        self.project_rows: dict[str, ProjectContext] = {}
        self.current_project: ProjectContext | None = None
        self.current_plan = ExecutionPlanState()
        self.selected_step_id: str | None = None
        self.flow_node_tags: dict[str, list[int]] = {}
        self._orchestrator_instance: Orchestrator | None = None
        self._orchestrator_root: Path | None = None

        self._configure_style()
        self._build_layout()
        self._show_stage("setup")
        self._schedule_queue_poll()
        self.refresh_projects()

    def _configure_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("App.TFrame", background="#eef2f6")
        style.configure("Card.TLabelframe", background="#ffffff", borderwidth=1)
        style.configure("Card.TLabelframe.Label", background="#ffffff", foreground="#1f2937", font=("Malgun Gothic", 10, "bold"))
        style.configure("Hero.TLabel", background="#132238", foreground="#f8fafc", font=("Malgun Gothic", 22, "bold"))
        style.configure("HeroSub.TLabel", background="#132238", foreground="#cbd5e1", font=("Malgun Gothic", 10))
        style.configure("Muted.TLabel", background="#eef2f6", foreground="#475569", font=("Malgun Gothic", 10))
        style.configure("Stage.TLabel", background="#eef2f6", foreground="#0f172a", font=("Malgun Gothic", 14, "bold"))

    def _build_layout(self) -> None:
        root_frame = ttk.Frame(self.root, padding=16, style="App.TFrame")
        root_frame.pack(fill=BOTH, expand=True)

        hero = ttk.Frame(root_frame, style="App.TFrame")
        hero.pack(fill=X)
        ttk.Label(hero, text="codex-auto", style="Hero.TLabel", anchor="w", padding=(18, 18, 18, 4)).pack(fill=X)
        ttk.Label(
            hero,
            text="GitHub login and Codex CLI login are assumed. Stage 1 prepares a local project directory. Stage 2 builds and runs an editable test-driven flow.",
            style="HeroSub.TLabel",
            anchor="w",
            padding=(18, 0, 18, 18),
        ).pack(fill=X)

        stage_row = ttk.Frame(root_frame, style="App.TFrame")
        stage_row.pack(fill=X, pady=(12, 8))
        ttk.Label(stage_row, textvariable=self.stage_title_var, style="Stage.TLabel").pack(side=LEFT)
        ttk.Label(stage_row, textvariable=self.status_var, style="Muted.TLabel").pack(side=RIGHT)

        main = ttk.Panedwindow(root_frame, orient="vertical")
        main.pack(fill=BOTH, expand=True)

        self.stage_container = ttk.Frame(main, style="App.TFrame")
        bottom = ttk.Frame(main, style="App.TFrame")
        main.add(self.stage_container, weight=72)
        main.add(bottom, weight=28)

        self.setup_stage = ttk.Frame(self.stage_container, style="App.TFrame")
        self.flow_stage = ttk.Frame(self.stage_container, style="App.TFrame")
        self._build_setup_stage(self.setup_stage)
        self._build_flow_stage(self.flow_stage)

        self._build_bottom_panel(bottom)

    def _build_setup_stage(self, parent: ttk.Frame) -> None:
        top_bar = ttk.Frame(parent, style="App.TFrame")
        top_bar.pack(fill=X, pady=(0, 12))
        ttk.Label(top_bar, text="Workspace Root", style="Muted.TLabel").pack(side=LEFT)
        ttk.Entry(top_bar, textvariable=self.workspace_root_var, width=60).pack(side=LEFT, padx=(8, 8), fill=X, expand=True)
        ttk.Button(top_bar, text="Browse", command=self._choose_workspace_root).pack(side=LEFT)
        ttk.Button(top_bar, text="Refresh", command=self.refresh_projects).pack(side=LEFT, padx=(8, 0))

        split = ttk.Panedwindow(parent, orient="horizontal")
        split.pack(fill=BOTH, expand=True)

        left = ttk.LabelFrame(split, text="Managed Projects", padding=12, style="Card.TLabelframe")
        right = ttk.LabelFrame(split, text="Environment Setup", padding=12, style="Card.TLabelframe")
        split.add(left, weight=44)
        split.add(right, weight=56)

        columns = ("name", "branch", "status", "updated", "path")
        self.project_tree = ttk.Treeview(left, columns=columns, show="headings", height=18)
        for key, title, width in [
            ("name", "Project", 180),
            ("branch", "Branch", 100),
            ("status", "Status", 160),
            ("updated", "Updated", 170),
            ("path", "Directory", 430),
        ]:
            self.project_tree.heading(key, text=title)
            self.project_tree.column(key, width=width, anchor=W)
        self.project_tree.pack(fill=BOTH, expand=True)
        self.project_tree.bind("<<TreeviewSelect>>", self._on_project_selected)

        project_actions = ttk.Frame(left)
        project_actions.pack(fill=X, pady=(10, 0))
        ttk.Button(project_actions, text="Open Flow", command=self.open_selected_project).pack(side=LEFT)
        ttk.Button(project_actions, text="Load Into Form", command=self.load_selected_project_into_form).pack(side=LEFT, padx=(8, 0))

        self.project_summary_text = ScrolledText(left, height=10, wrap="word")
        self.project_summary_text.pack(fill=BOTH, expand=False, pady=(12, 0))

        form = ttk.Frame(right)
        form.pack(fill=BOTH, expand=True)
        form.columnconfigure(1, weight=1)

        rows = [
            ("Project Directory", self.project_dir_var),
            ("Branch", self.branch_var),
            ("Origin URL (optional)", self.origin_url_var),
            ("Default Test Command", self.test_cmd_var),
        ]
        for row, (label, variable) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky=W, padx=(0, 12), pady=8)
            ttk.Entry(form, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=8)
            if label == "Project Directory":
                ttk.Button(form, text="Browse", command=self._choose_project_dir).grid(row=row, column=2, padx=(8, 0), pady=8)

        ttk.Label(form, text="Model").grid(row=4, column=0, sticky=W, padx=(0, 12), pady=8)
        ttk.Combobox(form, textvariable=self.model_var, values=["gpt-5.4", "gpt-5"], width=20).grid(row=4, column=1, sticky=W, pady=8)

        ttk.Label(form, text="Reasoning Effort").grid(row=5, column=0, sticky=W, padx=(0, 12), pady=8)
        ttk.Combobox(form, textvariable=self.effort_var, values=["low", "medium", "high", "xhigh"], state="readonly", width=20).grid(row=5, column=1, sticky=W, pady=8)

        ttk.Label(form, text="Max Planned Steps").grid(row=6, column=0, sticky=W, padx=(0, 12), pady=8)
        ttk.Entry(form, textvariable=self.max_steps_var, width=10).grid(row=6, column=1, sticky=W, pady=8)

        assumptions = ttk.LabelFrame(form, text="Assumptions and Fixed Runtime", padding=12, style="Card.TLabelframe")
        assumptions.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(16, 0))
        for text in [
            "GitHub login and Codex CLI login already exist on this machine.",
            "Codex execution uses approval=never and sandbox=danger-full-access.",
            "Stage 1 creates `.venv` and ensures `.gitignore` covers common Python artifacts.",
            "Stage execution commits and pushes after each verified step when `origin` is configured.",
        ]:
            ttk.Label(assumptions, text=text, style="Muted.TLabel", anchor="w").pack(fill=X, pady=2)

        setup_actions = ttk.Frame(form)
        setup_actions.grid(row=8, column=0, columnspan=3, sticky="w", pady=(18, 0))
        ttk.Button(setup_actions, text="Prepare Environment and Open Flow", command=self.prepare_environment).pack(side=LEFT)
        ttk.Button(setup_actions, text="Open Current Flow", command=self.open_selected_project).pack(side=LEFT, padx=(8, 0))

    def _build_flow_stage(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent, style="App.TFrame")
        header.pack(fill=X, pady=(0, 12))
        ttk.Button(header, text="Back To Setup", command=lambda: self._show_stage("setup")).pack(side=LEFT)
        ttk.Label(header, textvariable=self.current_project_label_var, style="Stage.TLabel").pack(side=LEFT, padx=(12, 0))
        ttk.Label(header, textvariable=self.current_step_label_var, style="Muted.TLabel").pack(side=RIGHT)

        prompt_frame = ttk.LabelFrame(parent, text="Stage 2. Prompt And Plan", padding=12, style="Card.TLabelframe")
        prompt_frame.pack(fill=X)
        self.prompt_text = ScrolledText(prompt_frame, height=5, wrap="word")
        self.prompt_text.pack(fill=X)

        prompt_actions = ttk.Frame(prompt_frame)
        prompt_actions.pack(fill=X, pady=(10, 0))
        ttk.Button(prompt_actions, text="Generate Plan With Codex", command=self.generate_plan).pack(side=LEFT)
        ttk.Button(prompt_actions, text="Save Edited Plan", command=self.save_plan).pack(side=LEFT, padx=(8, 0))
        ttk.Button(prompt_actions, text="Reset Plan", command=self.reset_plan).pack(side=LEFT, padx=(8, 0))
        ttk.Button(prompt_actions, text="Run Remaining Steps", command=self.run_plan).pack(side=LEFT, padx=(8, 0))
        ttk.Button(prompt_actions, text="Run Closeout", command=self.run_closeout).pack(side=LEFT, padx=(8, 0))
        ttk.Button(prompt_actions, text="Stop After Current Step", command=self.stop_after_current_step).pack(side=LEFT, padx=(8, 0))
        ttk.Button(prompt_actions, text="Reload Project", command=self.reload_current_project).pack(side=LEFT, padx=(8, 0))

        split = ttk.Panedwindow(parent, orient="horizontal")
        split.pack(fill=BOTH, expand=True, pady=(12, 0))

        flow_panel = ttk.LabelFrame(split, text="Interactive Flow", padding=12, style="Card.TLabelframe")
        editor_panel = ttk.LabelFrame(split, text="Selected Step", padding=12, style="Card.TLabelframe")
        split.add(flow_panel, weight=60)
        split.add(editor_panel, weight=40)

        flow_canvas_wrap = ttk.Frame(flow_panel)
        flow_canvas_wrap.pack(fill=BOTH, expand=True)
        self.flow_canvas = Canvas(flow_canvas_wrap, background="#ffffff", highlightthickness=0)
        flow_x = ttk.Scrollbar(flow_canvas_wrap, orient="horizontal", command=self.flow_canvas.xview)
        flow_y = ttk.Scrollbar(flow_canvas_wrap, orient="vertical", command=self.flow_canvas.yview)
        self.flow_canvas.configure(xscrollcommand=flow_x.set, yscrollcommand=flow_y.set)
        self.flow_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        flow_y.pack(side=RIGHT, fill=Y)
        flow_x.pack(fill=X)

        ttk.Label(
            flow_panel,
            text="Flow is editable for pending steps only. Each completed node represents a verified checkpoint with commit/push when available.",
            style="Muted.TLabel",
            anchor="w",
        ).pack(fill=X, pady=(10, 0))

        editor_panel.columnconfigure(1, weight=1)
        ttk.Label(editor_panel, text="Step ID").grid(row=0, column=0, sticky=W, padx=(0, 10), pady=6)
        ttk.Label(editor_panel, textvariable=self.selected_step_id_var).grid(row=0, column=1, sticky=W, pady=6)
        ttk.Label(editor_panel, text="Status").grid(row=1, column=0, sticky=W, padx=(0, 10), pady=6)
        ttk.Label(editor_panel, textvariable=self.selected_step_status_var).grid(row=1, column=1, sticky=W, pady=6)

        ttk.Label(editor_panel, text="Title").grid(row=2, column=0, sticky=W, padx=(0, 10), pady=6)
        self.step_title_var = StringVar()
        self.step_title_entry = ttk.Entry(editor_panel, textvariable=self.step_title_var)
        self.step_title_entry.grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(editor_panel, text="Test Command").grid(row=3, column=0, sticky=W, padx=(0, 10), pady=6)
        self.step_test_var = StringVar()
        self.step_test_entry = ttk.Entry(editor_panel, textvariable=self.step_test_var)
        self.step_test_entry.grid(row=3, column=1, sticky="ew", pady=6)

        ttk.Label(editor_panel, text="Display Description").grid(row=4, column=0, sticky="nw", padx=(0, 10), pady=6)
        self.step_description_text = ScrolledText(editor_panel, height=5, wrap="word")
        self.step_description_text.grid(row=4, column=1, sticky="ew", pady=6)

        ttk.Label(editor_panel, text="Codex Instruction").grid(row=5, column=0, sticky="nw", padx=(0, 10), pady=6)
        self.step_codex_text = ScrolledText(editor_panel, height=6, wrap="word")
        self.step_codex_text.grid(row=5, column=1, sticky="ew", pady=6)

        ttk.Label(editor_panel, text="Success Criteria").grid(row=6, column=0, sticky="nw", padx=(0, 10), pady=6)
        self.step_success_text = ScrolledText(editor_panel, height=4, wrap="word")
        self.step_success_text.grid(row=6, column=1, sticky="ew", pady=6)

        actions = ttk.Frame(editor_panel)
        actions.grid(row=7, column=0, columnspan=2, sticky="w", pady=(14, 0))
        ttk.Button(actions, text="Save Step", command=self.save_selected_step).pack(side=LEFT)
        ttk.Button(actions, text="Add Step", command=self.add_step_after_selection).pack(side=LEFT, padx=(8, 0))
        ttk.Button(actions, text="Delete Step", command=self.delete_selected_step).pack(side=LEFT, padx=(8, 0))
        ttk.Button(actions, text="Move Up", command=lambda: self.move_selected_step(-1)).pack(side=LEFT, padx=(8, 0))
        ttk.Button(actions, text="Move Down", command=lambda: self.move_selected_step(1)).pack(side=LEFT, padx=(8, 0))
        ttk.Button(actions, text="Clear Selection", command=self.clear_step_selection).pack(side=LEFT, padx=(8, 0))

    def _build_bottom_panel(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=BOTH, expand=True)

        activity_tab = ttk.Frame(notebook)
        snapshot_tab = ttk.Frame(notebook)
        notebook.add(activity_tab, text="Activity")
        notebook.add(snapshot_tab, text="Snapshot")

        self.log_text = ScrolledText(activity_tab, height=12, wrap="word")
        self.log_text.pack(fill=BOTH, expand=True)
        self.snapshot_text = ScrolledText(snapshot_tab, height=12, wrap="word")
        self.snapshot_text.pack(fill=BOTH, expand=True)

    def _show_stage(self, name: str) -> None:
        for child in self.stage_container.winfo_children():
            child.pack_forget()
        if name == "flow":
            self.stage_title_var.set("Stage 2. Prompt, Editable Flow, and Execution")
            self.flow_stage.pack(fill=BOTH, expand=True)
            return
        self.stage_title_var.set("Stage 1. Environment Setup")
        self.setup_stage.pack(fill=BOTH, expand=True)

    def _set_busy(self, busy: bool, status_text: str) -> None:
        self.busy = busy
        self.status_var.set(status_text)

    def _append_log(self, text: str) -> None:
        self.log_text.insert(END, text.rstrip() + "\n")
        self.log_text.see(END)

    def _set_snapshot(self, payload: object) -> None:
        if isinstance(payload, str):
            text = payload
        else:
            text = json.dumps(payload, indent=2, ensure_ascii=False)
        self.snapshot_text.delete("1.0", END)
        self.snapshot_text.insert("1.0", text)

    def _schedule_queue_poll(self) -> None:
        self.root.after(75, self._poll_queue)

    def _poll_queue(self) -> None:
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(payload))
            elif kind == "status":
                self.status_var.set(str(payload))
            elif kind == "projects":
                self._render_project_list(payload if isinstance(payload, list) else [])
            elif kind == "project_row":
                if isinstance(payload, ProjectContext):
                    self._upsert_project_row(payload)
            elif kind == "loaded_project":
                project, plan_state, switch_to_flow = payload  # type: ignore[misc]
                self._load_project_into_ui(project, plan_state, switch_to_flow=bool(switch_to_flow))
            elif kind == "snapshot":
                self._set_snapshot(payload)
            elif kind == "done":
                self._set_busy(False, str(payload))
            elif kind == "error":
                self._set_busy(False, str(payload))
                messagebox.showerror("codex-auto", str(payload))
        self._schedule_queue_poll()

    def _orchestrator(self) -> Orchestrator:
        workspace_root = Path(self.workspace_root_var.get().strip() or ".codex-auto-workspace").resolve()
        if self._orchestrator_instance is None or self._orchestrator_root != workspace_root:
            self._orchestrator_instance = Orchestrator(workspace_root)
            self._orchestrator_root = workspace_root
        return self._orchestrator_instance

    def _runtime(self) -> RuntimeOptions:
        try:
            max_blocks = max(1, int(self.max_steps_var.get().strip() or "5"))
        except ValueError as exc:
            raise ValueError("Max planned steps must be an integer.") from exc
        effort = self.effort_var.get().strip().lower() or "medium"
        if effort not in {"low", "medium", "high", "xhigh"}:
            raise ValueError("Reasoning effort must be one of low, medium, high, xhigh.")
        return RuntimeOptions(
            model=self.model_var.get().strip() or "gpt-5.4",
            effort=effort,
            approval_mode="never",
            sandbox_mode="danger-full-access",
            test_cmd=self.test_cmd_var.get().strip() or "python -m pytest",
            max_blocks=max_blocks,
            allow_push=True,
            require_checkpoint_approval=False,
            checkpoint_interval_blocks=1,
        )

    def _selected_project(self) -> ProjectContext | None:
        selection = self.project_tree.selection()
        if not selection:
            return None
        return self.project_rows.get(selection[0])

    def _project_dir(self) -> Path:
        project_dir = self.project_dir_var.get().strip()
        if not project_dir:
            raise ValueError("Project directory is required.")
        return Path(project_dir)

    def _prompt_value(self) -> str:
        return self.prompt_text.get("1.0", END).strip()

    def _choose_workspace_root(self) -> None:
        chosen = filedialog.askdirectory(initialdir=str(Path.cwd()))
        if chosen:
            self.workspace_root_var.set(chosen)
            self.refresh_projects()

    def _choose_project_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=str(Path.cwd()))
        if chosen:
            self.project_dir_var.set(chosen)

    def _run_async(self, label: str, worker: callable) -> None:
        if self.busy:
            messagebox.showinfo("codex-auto", "Another background task is already running.")
            return
        self._set_busy(True, f"{label} in progress")
        self._append_log(f"[start] {label}")

        def target() -> None:
            try:
                worker()
                self.queue.put(("done", f"{label} completed"))
                self.queue.put(("log", f"[done] {label}"))
            except Exception as exc:
                self.queue.put(("log", f"[error] {label}: {exc}\n{traceback.format_exc()}"))
                self.queue.put(("error", f"{label} failed: {exc}"))

        threading.Thread(target=target, daemon=True).start()

    def refresh_projects(self) -> None:
        orchestrator = self._orchestrator()

        def worker() -> None:
            projects = orchestrator.list_projects()
            self.queue.put(("projects", projects))
            self.queue.put(("snapshot", self._workspace_snapshot(projects)))

        self._run_async("Refresh projects", worker)

    def _workspace_snapshot(self, projects: list[ProjectContext]) -> dict[str, object]:
        running = 0
        ready = 0
        failed = 0
        for project in projects:
            status = project.metadata.current_status
            if status.startswith("running:"):
                running += 1
            elif status in {"setup_ready", "plan_ready", "plan_completed", "closed_out", "ready"}:
                ready += 1
            elif status.endswith("failed") or status in {"failed", "closeout_failed"}:
                failed += 1
        return {
            "workspace_root": str(Path(self.workspace_root_var.get().strip() or ".codex-auto-workspace").resolve()),
            "project_count": len(projects),
            "ready_like": ready,
            "running": running,
            "failed": failed,
        }

    def _render_project_list(self, projects: list[ProjectContext]) -> None:
        self.project_rows = {}
        selected = self.project_tree.selection()
        selected_id = selected[0] if selected else None
        for item in self.project_tree.get_children():
            self.project_tree.delete(item)
        for project in projects:
            self.project_rows[project.metadata.repo_id] = project
            self.project_tree.insert(
                "",
                END,
                iid=project.metadata.repo_id,
                values=(
                    project.metadata.display_name or project.metadata.slug,
                    project.metadata.branch,
                    project.metadata.current_status,
                    project.metadata.last_run_at or "",
                    str(project.metadata.repo_path),
                ),
            )
        if selected_id and selected_id in self.project_rows:
            self.project_tree.selection_set(selected_id)
            self._on_project_selected(None)
        elif self.current_project is not None:
            for repo_id, project in self.project_rows.items():
                if project.metadata.repo_id == self.current_project.metadata.repo_id:
                    self.project_tree.selection_set(repo_id)
                    self._on_project_selected(None)
                    break

    def _upsert_project_row(self, project: ProjectContext) -> None:
        repo_id = project.metadata.repo_id
        self.project_rows[repo_id] = project
        values = (
            project.metadata.display_name or project.metadata.slug,
            project.metadata.branch,
            project.metadata.current_status,
            project.metadata.last_run_at or "",
            str(project.metadata.repo_path),
        )
        if self.project_tree.exists(repo_id):
            self.project_tree.item(repo_id, values=values)
        else:
            self.project_tree.insert("", END, iid=repo_id, values=values)
        if self.current_project is not None and self.current_project.metadata.repo_id == repo_id:
            self.current_project = project

    def _project_summary(self, project: ProjectContext, plan_state: ExecutionPlanState | None = None) -> str:
        plan = plan_state or self._orchestrator().load_execution_plan_state(project)
        remaining = [step.step_id for step in plan.steps if step.status != "completed"]
        recent_blocks = read_jsonl_tail(project.paths.block_log_file, 5)
        return json.dumps(
            {
                "display_name": project.metadata.display_name or project.metadata.slug,
                "plan_title": plan.plan_title,
                "repo_path": str(project.metadata.repo_path),
                "origin_url": project.metadata.origin_url,
                "branch": project.metadata.branch,
                "status": project.metadata.current_status,
                "safe_revision": project.metadata.current_safe_revision,
                "default_test_command": plan.default_test_command or project.runtime.test_cmd,
                "closeout_status": plan.closeout_status,
                "closeout_report": str(project.paths.closeout_report_file),
                "closeout_commit_hash": plan.closeout_commit_hash,
                "remaining_steps": remaining,
                "recent_blocks": recent_blocks,
                "flow_svg": str(project.paths.execution_flow_svg_file),
            },
            indent=2,
            ensure_ascii=False,
        )

    def _on_project_selected(self, _event: object | None) -> None:
        project = self._selected_project()
        if project is None:
            return
        self.current_project = project
        self.project_summary_text.delete("1.0", END)
        self.project_summary_text.insert("1.0", self._project_summary(project))
        self.project_dir_var.set(str(project.metadata.repo_path))
        self.branch_var.set(project.metadata.branch)
        self.origin_url_var.set(project.metadata.origin_url or "")
        self.model_var.set(project.runtime.model)
        self.effort_var.set(project.runtime.effort)
        self.test_cmd_var.set(project.runtime.test_cmd)
        self.max_steps_var.set(str(project.runtime.max_blocks))

    def load_selected_project_into_form(self) -> None:
        project = self._selected_project()
        if project is None:
            messagebox.showinfo("codex-auto", "Select a managed project first.")
            return
        self._on_project_selected(None)
        self._append_log(f"[info] Loaded {project.metadata.display_name or project.metadata.slug} into the setup form.")

    def open_selected_project(self) -> None:
        project = self._selected_project()
        if project is None:
            try:
                project_dir = self._project_dir()
            except Exception as exc:
                messagebox.showerror("codex-auto", str(exc))
                return
            project = self._orchestrator().local_project(project_dir)
            if project is None:
                messagebox.showinfo("codex-auto", "Prepare the environment first or select a managed project.")
                return
        orchestrator = self._orchestrator()
        plan_state = orchestrator.load_execution_plan_state(project)
        self._load_project_into_ui(project, plan_state, switch_to_flow=True)

    def prepare_environment(self) -> None:
        try:
            project_dir = self._project_dir()
            runtime = self._runtime()
            branch = self.branch_var.get().strip() or "main"
            origin_url = self.origin_url_var.get().strip()
        except Exception as exc:
            messagebox.showerror("codex-auto", str(exc))
            return

        orchestrator = self._orchestrator()

        def worker() -> None:
            project = orchestrator.setup_local_project(
                project_dir=project_dir,
                runtime=runtime,
                branch=branch,
                origin_url=origin_url,
            )
            plan_state = orchestrator.load_execution_plan_state(project)
            self.queue.put(("loaded_project", (project, plan_state, True)))
            self.queue.put(("project_row", project))
            self.queue.put(("snapshot", self._project_summary(project, plan_state)))

        self._run_async("Prepare environment", worker)

    def generate_plan(self) -> None:
        if self.current_project is None:
            messagebox.showinfo("codex-auto", "Prepare or open a project first.")
            return
        prompt = self._prompt_value()
        if not prompt:
            messagebox.showerror("codex-auto", "Prompt is required to generate the plan.")
            return
        if any(step.status == "completed" for step in self.current_plan.steps):
            messagebox.showerror("codex-auto", "The plan already has completed steps. Edit the remaining steps manually instead of regenerating.")
            return
        if self.current_plan.steps and not messagebox.askyesno("codex-auto", "Replace the current unstarted plan with a new Codex-generated plan?"):
            return

        try:
            runtime = self._runtime()
            project_dir = Path(self.current_project.metadata.repo_path)
            branch = self.current_project.metadata.branch
            origin_url = self.current_project.metadata.origin_url or self.origin_url_var.get().strip()
            max_steps = max(1, int(self.max_steps_var.get().strip() or "5"))
        except Exception as exc:
            messagebox.showerror("codex-auto", str(exc))
            return

        orchestrator = self._orchestrator()

        def worker() -> None:
            project, plan_state = orchestrator.generate_execution_plan(
                project_dir=project_dir,
                runtime=runtime,
                project_prompt=prompt,
                branch=branch,
                max_steps=max_steps,
                origin_url=origin_url,
            )
            self.queue.put(("loaded_project", (project, plan_state, True)))
            self.queue.put(("project_row", project))
            self.queue.put(("snapshot", self._project_summary(project, plan_state)))

        self._run_async("Generate plan", worker)

    def save_plan(self) -> None:
        if self.current_project is None:
            messagebox.showinfo("codex-auto", "Open a project first.")
            return
        try:
            runtime = self._runtime()
            plan_state = self._plan_from_widgets()
            project_dir = Path(self.current_project.metadata.repo_path)
            branch = self.current_project.metadata.branch
            origin_url = self.current_project.metadata.origin_url or self.origin_url_var.get().strip()
        except Exception as exc:
            messagebox.showerror("codex-auto", str(exc))
            return

        orchestrator = self._orchestrator()

        def worker() -> None:
            project, saved = orchestrator.update_execution_plan(
                project_dir=project_dir,
                runtime=runtime,
                plan_state=plan_state,
                branch=branch,
                origin_url=origin_url,
            )
            self.queue.put(("loaded_project", (project, saved, True)))
            self.queue.put(("project_row", project))
            self.queue.put(("snapshot", self._project_summary(project, saved)))

        self._run_async("Save edited plan", worker)

    def reset_plan(self) -> None:
        if self.current_project is None:
            messagebox.showinfo("codex-auto", "Open a project first.")
            return
        has_content = bool(self.current_plan.steps or self.current_plan.summary.strip() or self._prompt_value())
        if not has_content:
            messagebox.showinfo("codex-auto", "The current plan is already empty.")
            return
        completed = [step.step_id for step in self.current_plan.steps if step.status == "completed"]
        prompt = "Reset the saved prompt and remove all execution steps for this project?"
        if completed:
            prompt += f"\n\nCompleted steps will also be cleared: {', '.join(completed)}."
        if not messagebox.askyesno("codex-auto", prompt):
            return
        try:
            runtime = self._runtime()
            project_dir = Path(self.current_project.metadata.repo_path)
            branch = self.current_project.metadata.branch
            origin_url = self.current_project.metadata.origin_url or self.origin_url_var.get().strip()
            empty_plan = ExecutionPlanState(default_test_command=self.test_cmd_var.get().strip() or runtime.test_cmd)
        except Exception as exc:
            messagebox.showerror("codex-auto", str(exc))
            return

        orchestrator = self._orchestrator()

        def worker() -> None:
            project, saved = orchestrator.update_execution_plan(
                project_dir=project_dir,
                runtime=runtime,
                plan_state=empty_plan,
                branch=branch,
                origin_url=origin_url,
            )
            self.queue.put(("loaded_project", (project, saved, True)))
            self.queue.put(("project_row", project))
            self.queue.put(("snapshot", self._project_summary(project, saved)))

        self._run_async("Reset plan", worker)

    def run_plan(self) -> None:
        if self.current_project is None:
            messagebox.showinfo("codex-auto", "Open a project first.")
            return
        try:
            runtime = self._runtime()
            plan_state = self._plan_from_widgets()
            if not plan_state.steps:
                raise ValueError("Create or add at least one planned step first.")
            project_dir = Path(self.current_project.metadata.repo_path)
            branch = self.current_project.metadata.branch
            origin_url = self.current_project.metadata.origin_url or self.origin_url_var.get().strip()
        except Exception as exc:
            messagebox.showerror("codex-auto", str(exc))
            return

        self.stop_after_step_event.clear()
        orchestrator = self._orchestrator()

        def worker() -> None:
            project, saved = orchestrator.update_execution_plan(
                project_dir=project_dir,
                runtime=runtime,
                plan_state=plan_state,
                branch=branch,
                origin_url=origin_url,
            )
            self.queue.put(("loaded_project", (project, saved, True)))
            self.queue.put(("project_row", project))
            self.queue.put(("snapshot", self._project_summary(project, saved)))
            for step in [item for item in saved.steps if item.status != "completed"]:
                if self.stop_after_step_event.is_set():
                    self.queue.put(("log", "[info] Stop requested. Execution paused before the next step."))
                    break
                running_project = deepcopy(project)
                running_project.metadata.current_status = f"running:step:{step.step_id}"
                running_plan = _plan_state_with_running_step(saved, step.step_id)
                self.queue.put(("loaded_project", (running_project, running_plan, True)))
                self.queue.put(("project_row", running_project))
                self.queue.put(("status", f"Running {step.step_id}: {step.title}"))
                self.queue.put(("log", f"[run] {step.step_id} - {step.title}"))
                try:
                    project, saved, result_step = orchestrator.run_saved_execution_step(
                        project_dir=project_dir,
                        runtime=runtime,
                        step_id=step.step_id,
                        branch=branch,
                        origin_url=origin_url,
                    )
                except Exception:
                    latest_project = orchestrator.local_project(project_dir)
                    if latest_project is not None:
                        latest_plan = orchestrator.load_execution_plan_state(latest_project)
                        self.queue.put(("loaded_project", (latest_project, latest_plan, True)))
                        self.queue.put(("project_row", latest_project))
                        self.queue.put(("snapshot", self._project_summary(latest_project, latest_plan)))
                    raise
                self.queue.put(("loaded_project", (project, saved, True)))
                self.queue.put(("project_row", project))
                self.queue.put(("snapshot", self._project_summary(project, saved)))
                self.queue.put(("log", f"[step] {result_step.step_id} -> {result_step.status}"))
                if result_step.status != "completed":
                    break
            self.queue.put(("status", "Ready"))

        self._run_async("Run remaining steps", worker)

    def run_closeout(self) -> None:
        if self.current_project is None:
            messagebox.showinfo("codex-auto", "Open a project first.")
            return
        try:
            plan_state = self._plan_from_widgets()
            if not plan_state.steps:
                raise ValueError("Create and complete the execution plan before running closeout.")
            if any(step.status != "completed" for step in plan_state.steps):
                raise ValueError("Closeout can run only after all steps are completed.")
            runtime = self._runtime()
            project_dir = Path(self.current_project.metadata.repo_path)
            branch = self.current_project.metadata.branch
            origin_url = self.current_project.metadata.origin_url or self.origin_url_var.get().strip()
        except Exception as exc:
            messagebox.showerror("codex-auto", str(exc))
            return
        if not messagebox.askyesno(
            "codex-auto",
            "Run final closeout now? This will do final cleanup, verification, optional runnable smoke checks, and docs handoff work.",
        ):
            return

        orchestrator = self._orchestrator()

        def worker() -> None:
            running_project = deepcopy(self.current_project) if self.current_project is not None else None
            if running_project is not None:
                running_project.metadata.current_status = "running:closeout"
                self.queue.put(("loaded_project", (running_project, _plan_state_with_closeout_status(plan_state, "running"), True)))
                self.queue.put(("project_row", running_project))
            self.queue.put(("status", "Running project closeout"))
            self.queue.put(("log", "[run] project closeout"))
            project, saved = orchestrator.run_execution_closeout(
                project_dir=project_dir,
                runtime=runtime,
                branch=branch,
                origin_url=origin_url,
            )
            self.queue.put(("loaded_project", (project, saved, True)))
            self.queue.put(("project_row", project))
            self.queue.put(("snapshot", self._project_summary(project, saved)))
            self.queue.put(("log", f"[closeout] {saved.closeout_status}"))

        self._run_async("Run closeout", worker)

    def stop_after_current_step(self) -> None:
        if not self.busy:
            self._append_log("[info] No active execution is running.")
            return
        self.stop_after_step_event.set()
        self.status_var.set("Stop requested after current step")
        self._append_log("[info] Stop requested. The current step will finish, then execution will pause.")

    def reload_current_project(self) -> None:
        if self.current_project is None:
            messagebox.showinfo("codex-auto", "No project is open.")
            return
        orchestrator = self._orchestrator()
        latest = orchestrator.local_project(Path(self.current_project.metadata.repo_path))
        if latest is None:
            messagebox.showerror("codex-auto", "The project is no longer registered in this workspace.")
            return
        plan_state = orchestrator.load_execution_plan_state(latest)
        self._load_project_into_ui(latest, plan_state, switch_to_flow=True)
        self._append_log(f"[info] Reloaded {latest.metadata.display_name or latest.metadata.slug}.")

    def _load_project_into_ui(self, project: ProjectContext, plan_state: ExecutionPlanState, switch_to_flow: bool) -> None:
        self.current_project = project
        self.current_plan = plan_state
        self.project_dir_var.set(str(project.metadata.repo_path))
        self.branch_var.set(project.metadata.branch)
        self.origin_url_var.set(project.metadata.origin_url or "")
        self.model_var.set(project.runtime.model)
        self.effort_var.set(project.runtime.effort)
        self.test_cmd_var.set(plan_state.default_test_command or project.runtime.test_cmd)
        self.max_steps_var.set(str(max(len(plan_state.steps), project.runtime.max_blocks, 1)))
        project_label = project.metadata.display_name or project.metadata.slug
        if plan_state.plan_title.strip():
            project_label = f"{project_label} | {plan_state.plan_title.strip()}"
        self.current_project_label_var.set(f"{project_label}  [{project.metadata.branch}]")
        self.current_step_label_var.set(self._progress_caption(plan_state))
        self.prompt_text.delete("1.0", END)
        self.prompt_text.insert("1.0", plan_state.project_prompt)
        self.clear_step_selection(redraw=False)
        if plan_state.steps:
            first_selectable = next((step.step_id for step in plan_state.steps if step.status != "completed"), plan_state.steps[0].step_id)
            self.select_step(first_selectable)
        else:
            self._set_editor_fields(None)
        self._draw_flow_chart()
        self._set_snapshot(
            {
                "project": project.metadata.to_dict(),
                "runtime": project.runtime.to_dict(),
                "plan": plan_state.to_dict(),
            }
        )
        if switch_to_flow:
            self._show_stage("flow")

    def _progress_caption(self, plan_state: ExecutionPlanState) -> str:
        completed = len([step for step in plan_state.steps if step.status == "completed"])
        total = len(plan_state.steps)
        if total == 0:
            return "No plan yet"
        if completed == total:
            if plan_state.closeout_status == "completed":
                return f"Completed {completed}/{total} steps, closeout completed"
            if plan_state.closeout_status == "running":
                return f"Completed {completed}/{total} steps, closeout running"
            if plan_state.closeout_status == "failed":
                return f"Completed {completed}/{total} steps, closeout failed"
            return f"Completed {completed}/{total} steps, closeout pending"
        next_step = next((step.step_id for step in plan_state.steps if step.status != "completed"), "done")
        return f"Completed {completed}/{total} steps, next: {next_step}"

    def _plan_from_widgets(self) -> ExecutionPlanState:
        self._sync_selected_step_into_plan()
        cleaned_steps = [step for step in self.current_plan.steps if step.title.strip()]
        if not cleaned_steps and self._prompt_value():
            raise ValueError("There is a prompt, but the editable flow is empty. Generate a plan or add steps manually.")
        return ExecutionPlanState(
            plan_title=self.current_plan.plan_title.strip(),
            project_prompt=self._prompt_value(),
            summary=self.current_plan.summary.strip(),
            default_test_command=self.test_cmd_var.get().strip() or "python -m pytest",
            last_updated_at=self.current_plan.last_updated_at,
            closeout_status=self.current_plan.closeout_status,
            closeout_started_at=self.current_plan.closeout_started_at,
            closeout_completed_at=self.current_plan.closeout_completed_at,
            closeout_commit_hash=self.current_plan.closeout_commit_hash,
            closeout_notes=self.current_plan.closeout_notes,
            steps=cleaned_steps,
        )

    def _selected_step(self) -> ExecutionStep | None:
        if not self.selected_step_id:
            return None
        for step in self.current_plan.steps:
            if step.step_id == self.selected_step_id:
                return step
        return None

    def _step_is_editable(self, step: ExecutionStep | None) -> bool:
        return step is not None and step.status == "pending"

    def _sync_selected_step_into_plan(self) -> None:
        step = self._selected_step()
        if step is None or not self._step_is_editable(step):
            return
        title = self.step_title_var.get().strip()
        test_command = self.step_test_var.get().strip() or self.test_cmd_var.get().strip() or "python -m pytest"
        if not title:
            raise ValueError("Selected step title cannot be empty.")
        step.title = title
        step.test_command = test_command
        step.display_description = self.step_description_text.get("1.0", END).strip()
        step.codex_description = self.step_codex_text.get("1.0", END).strip()
        step.success_criteria = self.step_success_text.get("1.0", END).strip()

    def select_step(self, step_id: str) -> None:
        try:
            self._sync_selected_step_into_plan()
        except ValueError:
            pass
        self.selected_step_id = step_id
        self._set_editor_fields(self._selected_step())
        self._draw_flow_chart()

    def clear_step_selection(self, redraw: bool = True) -> None:
        try:
            self._sync_selected_step_into_plan()
        except ValueError:
            pass
        self.selected_step_id = None
        self.selected_step_id_var.set("")
        self.selected_step_status_var.set("")
        self._set_editor_fields(None)
        if redraw:
            self._draw_flow_chart()

    def _set_editor_fields(self, step: ExecutionStep | None) -> None:
        self.step_title_var.set("")
        self.step_test_var.set(self.test_cmd_var.get().strip() or "python -m pytest")
        self.step_description_text.configure(state="normal")
        self.step_codex_text.configure(state="normal")
        self.step_success_text.configure(state="normal")
        self.step_description_text.delete("1.0", END)
        self.step_codex_text.delete("1.0", END)
        self.step_success_text.delete("1.0", END)
        if step is None:
            editable = True
            self.selected_step_id_var.set("")
            self.selected_step_status_var.set("")
        else:
            editable = self._step_is_editable(step)
            self.selected_step_id_var.set(step.step_id)
            self.selected_step_status_var.set(step.status)
            self.step_title_var.set(step.title)
            self.step_test_var.set(step.test_command or self.test_cmd_var.get().strip() or "python -m pytest")
            self.step_description_text.insert("1.0", step.display_description)
            self.step_codex_text.insert("1.0", step.codex_description)
            self.step_success_text.insert("1.0", step.success_criteria)
        state = "normal" if editable else "disabled"
        self.step_title_entry.configure(state=state)
        self.step_test_entry.configure(state=state)
        self.step_description_text.configure(state=state)
        self.step_codex_text.configure(state=state)
        self.step_success_text.configure(state=state)

    def save_selected_step(self) -> None:
        step = self._selected_step()
        if step is None:
            messagebox.showinfo("codex-auto", "Select a pending step first.")
            return
        if not self._step_is_editable(step):
            messagebox.showinfo("codex-auto", "Only pending steps can be edited.")
            return
        try:
            self._sync_selected_step_into_plan()
        except Exception as exc:
            messagebox.showerror("codex-auto", str(exc))
            return
        self.current_step_label_var.set(self._progress_caption(self.current_plan))
        self._draw_flow_chart()
        self._append_log(f"[edit] Updated {step.step_id}.")

    def add_step_after_selection(self) -> None:
        try:
            self._sync_selected_step_into_plan()
        except Exception as exc:
            messagebox.showerror("codex-auto", str(exc))
            return
        insert_at = len(self.current_plan.steps)
        if self.selected_step_id:
            for index, step in enumerate(self.current_plan.steps):
                if step.step_id == self.selected_step_id:
                    if step.status != "pending":
                        messagebox.showinfo("codex-auto", "Insert new steps after a pending step, or clear the selection to append at the end.")
                        return
                    insert_at = index + 1
                    break
        new_step = ExecutionStep(
            step_id=f"LT{len(self.current_plan.steps) + 1}",
            title="New pending step",
            display_description="Describe the checkpoint for the user.",
            codex_description="Describe the implementation work Codex should perform for this checkpoint.",
            test_command=self.test_cmd_var.get().strip() or "python -m pytest",
            status="pending",
        )
        self.current_plan.steps.insert(insert_at, new_step)
        self.select_step(new_step.step_id)
        self.current_step_label_var.set(self._progress_caption(self.current_plan))
        self._append_log("[edit] Added a pending step.")

    def delete_selected_step(self) -> None:
        step = self._selected_step()
        if step is None:
            messagebox.showinfo("codex-auto", "Select a step first.")
            return
        if not self._step_is_editable(step):
            messagebox.showinfo("codex-auto", "Only pending steps can be deleted.")
            return
        self.current_plan.steps = [item for item in self.current_plan.steps if item.step_id != step.step_id]
        self.clear_step_selection(redraw=False)
        self.current_step_label_var.set(self._progress_caption(self.current_plan))
        self._draw_flow_chart()
        self._append_log(f"[edit] Deleted {step.step_id}.")

    def move_selected_step(self, direction: int) -> None:
        step = self._selected_step()
        if step is None:
            messagebox.showinfo("codex-auto", "Select a pending step first.")
            return
        if not self._step_is_editable(step):
            messagebox.showinfo("codex-auto", "Only pending steps can be reordered.")
            return
        try:
            self._sync_selected_step_into_plan()
        except Exception as exc:
            messagebox.showerror("codex-auto", str(exc))
            return
        index = next((i for i, item in enumerate(self.current_plan.steps) if item.step_id == step.step_id), -1)
        if index < 0:
            return
        target = index + direction
        if target < 0 or target >= len(self.current_plan.steps):
            return
        if self.current_plan.steps[target].status != "pending":
            messagebox.showinfo("codex-auto", "Pending steps can only move within the unstarted portion of the flow.")
            return
        self.current_plan.steps[index], self.current_plan.steps[target] = self.current_plan.steps[target], self.current_plan.steps[index]
        self.select_step(step.step_id)
        self._append_log(f"[edit] Reordered {step.step_id}.")

    def _draw_flow_chart(self) -> None:
        self.flow_canvas.delete("all")
        self.flow_node_tags = {}
        steps = self.current_plan.steps
        if not steps:
            self.flow_canvas.create_text(
                24,
                24,
                text="No plan yet. Generate one from the prompt or add steps manually.",
                anchor="w",
                fill="#64748b",
                font=("Malgun Gothic", 11),
            )
            self.flow_canvas.configure(scrollregion=(0, 0, 960, 320))
            return

        box_width = 250
        box_height = 120
        gap_x = 30
        gap_y = 36
        margin_x = 24
        margin_y = 24
        per_row = 3
        colors = {
            "completed": ("#0f766e", "#ecfeff"),
            "running": ("#1d4ed8", "#eff6ff"),
            "paused": ("#7c3aed", "#f5f3ff"),
            "failed": ("#b91c1c", "#fef2f2"),
            "pending": ("#cbd5e1", "#0f172a"),
        }

        for index, step in enumerate(steps):
            row = index // per_row
            col = index % per_row
            x1 = margin_x + col * (box_width + gap_x)
            y1 = margin_y + row * (box_height + gap_y)
            x2 = x1 + box_width
            y2 = y1 + box_height
            status = step.status if step.status in colors else "pending"
            fill, text_fill = colors[status]
            outline = "#0f172a" if step.step_id == self.selected_step_id else fill
            width = 3 if step.step_id == self.selected_step_id else 1
            tags = ("step", step.step_id)
            self.flow_canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=width, tags=tags)
            self.flow_canvas.create_text(x1 + 14, y1 + 18, text=step.step_id, anchor="w", fill=text_fill, font=("Malgun Gothic", 12, "bold"), tags=tags)
            self.flow_canvas.create_text(
                x1 + 14,
                y1 + 46,
                text=textwrap.shorten(step.title, width=38, placeholder="..."),
                anchor="w",
                fill=text_fill,
                font=("Malgun Gothic", 11, "bold"),
                tags=tags,
            )
            self.flow_canvas.create_text(
                x1 + 14,
                y1 + 74,
                text=textwrap.shorten(step.display_description or step.test_command or "No step summary.", width=42, placeholder="..."),
                anchor="w",
                fill=text_fill,
                font=("Malgun Gothic", 10),
                tags=tags,
            )
            self.flow_canvas.create_text(
                x1 + 14,
                y1 + 100,
                text=status,
                anchor="w",
                fill=text_fill,
                font=("Malgun Gothic", 10),
                tags=tags,
            )
            self.flow_canvas.tag_bind(step.step_id, "<Button-1>", lambda _event, step_id=step.step_id: self.select_step(step_id))

            if col < per_row - 1 and index + 1 < len(steps) and (index + 1) // per_row == row:
                center_y = y1 + box_height / 2
                start_x = x2 + 6
                end_x = x2 + gap_x - 6
                self.flow_canvas.create_line(start_x, center_y, end_x, center_y, fill="#94a3b8", width=4, arrow="last")

        rows = (len(steps) + per_row - 1) // per_row
        width = margin_x * 2 + per_row * box_width + max(0, per_row - 1) * gap_x
        height = margin_y * 2 + rows * box_height + max(0, rows - 1) * gap_y
        self.flow_canvas.configure(scrollregion=(0, 0, width, height))


def main() -> int:
    root = Tk()
    app = CodexAutoGUI(root)
    app._append_log("GUI ready")
    root.mainloop()
    return 0
