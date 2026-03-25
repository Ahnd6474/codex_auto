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

from .model_selection import (
    DEFAULT_CODEX_BASE_SLUG,
    DEFAULT_CODEX_VARIANT_SLUG,
    DEFAULT_MODEL_SLUG,
    MODEL_MODE_CODEX,
    MODEL_MODE_SLUG,
    ModelSelection,
    model_selection_from_runtime,
    normalize_model_mode,
    validate_reasoning_effort,
)
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
        self.root.configure(background="#f4efe8")

        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.stop_after_step_event = threading.Event()

        self.workspace_root_var = StringVar(value=".codex-auto-workspace")
        self.project_dir_var = StringVar()
        self.branch_var = StringVar(value="main")
        self.origin_url_var = StringVar()
        self.model_mode_var = StringVar(value=MODEL_MODE_SLUG)
        self.model_slug_input_var = StringVar(value=DEFAULT_MODEL_SLUG)
        self.codex_base_slug_var = StringVar(value=DEFAULT_CODEX_BASE_SLUG)
        self.codex_variant_slug_var = StringVar(value=DEFAULT_CODEX_VARIANT_SLUG)
        self.model_var = StringVar(value=DEFAULT_MODEL_SLUG)
        self.effort_var = StringVar(value="medium")
        self.runtime_summary_var = StringVar(value="")
        self.test_cmd_var = StringVar(value="python -m pytest")
        self.max_steps_var = StringVar(value="5")
        self.status_var = StringVar(value="Ready")
        self.stage_title_var = StringVar(value="Workspace Setup")
        self.stage_hint_var = StringVar(value="Choose a local repository and runtime model, then prepare the workspace.")
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
        for variable in (
            self.model_mode_var,
            self.model_slug_input_var,
            self.codex_base_slug_var,
            self.codex_variant_slug_var,
            self.effort_var,
        ):
            variable.trace_add("write", self._on_runtime_model_changed)

        self._configure_style()
        self._build_layout()
        self._load_runtime_inputs(RuntimeOptions())
        self._show_stage("setup")
        self._schedule_queue_poll()
        self.refresh_projects()

    def _configure_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        app_bg = "#f4efe8"
        panel_bg = "#fffaf5"
        surface_bg = "#fffdf9"
        hero_bg = "#2f4858"
        ink = "#22313a"
        soft_ink = "#6d7b83"
        border = "#e3d8cb"
        accent = "#c9795d"
        accent_active = "#b6664b"
        accent_soft = "#f6e2d7"
        style.configure("App.TFrame", background=app_bg)
        style.configure("Toolbar.TFrame", background=app_bg)
        style.configure("Hero.TFrame", background=hero_bg)
        style.configure("Card.TFrame", background=panel_bg)
        style.configure(
            "Card.TLabelframe",
            background=panel_bg,
            borderwidth=1,
            relief="solid",
            bordercolor=border,
            lightcolor=panel_bg,
            darkcolor=border,
        )
        style.configure("Card.TLabelframe.Label", background=panel_bg, foreground=ink, font=("Malgun Gothic", 10, "bold"))
        style.configure("Hero.TLabel", background=hero_bg, foreground="#fff8f2", font=("Malgun Gothic", 24, "bold"))
        style.configure("HeroSub.TLabel", background=hero_bg, foreground="#dbe7ec", font=("Malgun Gothic", 10))
        style.configure("HeroChip.TLabel", background="#40606f", foreground="#fff8f2", font=("Malgun Gothic", 9, "bold"))
        style.configure("Muted.TLabel", background=app_bg, foreground=soft_ink, font=("Malgun Gothic", 10))
        style.configure("CardMuted.TLabel", background=panel_bg, foreground=soft_ink, font=("Malgun Gothic", 10))
        style.configure("Field.TLabel", background=panel_bg, foreground=ink, font=("Malgun Gothic", 10, "bold"))
        style.configure("Value.TLabel", background=panel_bg, foreground=ink, font=("Malgun Gothic", 10))
        style.configure("Stage.TLabel", background=app_bg, foreground=ink, font=("Malgun Gothic", 18, "bold"))
        style.configure("StageHint.TLabel", background=app_bg, foreground=soft_ink, font=("Malgun Gothic", 10))
        style.configure("StatusPill.TLabel", background=accent_soft, foreground="#8a4d39", font=("Malgun Gothic", 10, "bold"))
        style.configure("Primary.TButton", background=accent, foreground="#fffaf6", padding=(16, 9), borderwidth=0, font=("Malgun Gothic", 10, "bold"))
        style.map(
            "Primary.TButton",
            background=[("active", accent_active), ("pressed", accent_active), ("disabled", "#dbc1b4")],
            foreground=[("disabled", "#fff6f1")],
        )
        style.configure("Secondary.TButton", background=surface_bg, foreground=ink, padding=(14, 9), borderwidth=1, bordercolor=border)
        style.map("Secondary.TButton", background=[("active", "#f6efe8"), ("pressed", "#efe6de")])
        style.configure("Quiet.TButton", background=panel_bg, foreground=soft_ink, padding=(12, 8), borderwidth=0)
        style.map("Quiet.TButton", background=[("active", "#f7f1ea"), ("pressed", "#f1e9e1")])
        style.configure("TEntry", fieldbackground=surface_bg, foreground=ink, bordercolor=border, insertcolor=ink, padding=8)
        style.configure("TCombobox", fieldbackground=surface_bg, foreground=ink, bordercolor=border, padding=7)
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", surface_bg)],
            background=[("readonly", surface_bg)],
            foreground=[("readonly", ink)],
        )
        style.configure("Treeview", background=surface_bg, fieldbackground=surface_bg, foreground=ink, rowheight=30, borderwidth=0)
        style.map("Treeview", background=[("selected", "#f3dfd2")], foreground=[("selected", ink)])
        style.configure("Treeview.Heading", background="#f7efe7", foreground="#5d4b43", relief="flat", padding=(10, 8), font=("Malgun Gothic", 9, "bold"))
        style.configure("TNotebook", background=app_bg, borderwidth=0)
        style.configure("TNotebook.Tab", background="#efe6dc", foreground="#6b5b53", padding=(16, 8), font=("Malgun Gothic", 9, "bold"))
        style.map("TNotebook.Tab", background=[("selected", panel_bg)], foreground=[("selected", ink)])
        style.configure("Card.TRadiobutton", background=panel_bg, foreground=ink, font=("Malgun Gothic", 10))

    def _build_layout(self) -> None:
        root_frame = ttk.Frame(self.root, padding=18, style="App.TFrame")
        root_frame.pack(fill=BOTH, expand=True)

        hero = ttk.Frame(root_frame, padding=0, style="Hero.TFrame")
        hero.pack(fill=X)
        hero_body = ttk.Frame(hero, padding=20, style="Hero.TFrame")
        hero_body.pack(fill=X)
        ttk.Label(hero_body, text="codex-auto", style="Hero.TLabel", anchor="w").pack(fill=X)
        ttk.Label(
            hero_body,
            text="Prepare a repo, choose the runtime model, generate a safe flow, and run it step by step.",
            style="HeroSub.TLabel",
            anchor="w",
            padding=(0, 8, 0, 0),
        ).pack(fill=X)
        hero_chips = ttk.Frame(hero_body, style="Hero.TFrame")
        hero_chips.pack(fill=X, pady=(14, 0))
        ttk.Label(hero_chips, text="Workspace setup", style="HeroChip.TLabel", padding=(10, 6)).pack(side=LEFT)
        ttk.Label(hero_chips, text="Model slug builder", style="HeroChip.TLabel", padding=(10, 6)).pack(side=LEFT, padx=(8, 0))
        ttk.Label(hero_chips, text="Editable flow execution", style="HeroChip.TLabel", padding=(10, 6)).pack(side=LEFT, padx=(8, 0))

        stage_row = ttk.Frame(root_frame, style="App.TFrame")
        stage_row.pack(fill=X, pady=(16, 10))
        stage_text = ttk.Frame(stage_row, style="App.TFrame")
        stage_text.pack(side=LEFT, fill=X, expand=True)
        ttk.Label(stage_text, textvariable=self.stage_title_var, style="Stage.TLabel").pack(anchor="w")
        ttk.Label(stage_text, textvariable=self.stage_hint_var, style="StageHint.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Label(stage_row, textvariable=self.status_var, style="StatusPill.TLabel", padding=(14, 8)).pack(side=RIGHT)

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
        ttk.Label(
            parent,
            text="Start here: pick a workspace, reopen an existing managed project if needed, or set up a new local repository.",
            style="Muted.TLabel",
            anchor="w",
        ).pack(fill=X, pady=(0, 10))

        top_bar = ttk.Frame(parent, style="Toolbar.TFrame")
        top_bar.pack(fill=X, pady=(0, 12))
        ttk.Label(top_bar, text="Workspace Root", style="Muted.TLabel").pack(side=LEFT)
        ttk.Entry(top_bar, textvariable=self.workspace_root_var, width=60).pack(side=LEFT, padx=(8, 8), fill=X, expand=True)
        ttk.Button(top_bar, text="Browse", command=self._choose_workspace_root, style="Secondary.TButton").pack(side=LEFT)
        ttk.Button(top_bar, text="Refresh", command=self.refresh_projects, style="Quiet.TButton").pack(side=LEFT, padx=(8, 0))

        split = ttk.Panedwindow(parent, orient="horizontal")
        split.pack(fill=BOTH, expand=True)

        left = ttk.LabelFrame(split, text="Managed Projects", padding=12, style="Card.TLabelframe")
        right = ttk.LabelFrame(split, text="Environment Setup", padding=12, style="Card.TLabelframe")
        split.add(left, weight=44)
        split.add(right, weight=56)

        ttk.Label(
            left,
            text="Open a managed project from the list, or load its settings back into the setup form before running again.",
            style="CardMuted.TLabel",
            anchor="w",
        ).pack(fill=X, pady=(0, 10))

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

        project_actions = ttk.Frame(left, style="Card.TFrame")
        project_actions.pack(fill=X, pady=(10, 0))
        ttk.Button(project_actions, text="Open Flow", command=self.open_selected_project, style="Primary.TButton").pack(side=LEFT)
        ttk.Button(project_actions, text="Load Into Form", command=self.load_selected_project_into_form, style="Secondary.TButton").pack(side=LEFT, padx=(8, 0))

        self.project_summary_text = ScrolledText(left, height=10, wrap="word")
        self.project_summary_text.pack(fill=BOTH, expand=False, pady=(12, 0))
        self._configure_text_surface(self.project_summary_text)
        self.project_summary_text.insert("1.0", "Project details and recent execution activity will appear here.")

        form = ttk.Frame(right, style="Card.TFrame")
        form.pack(fill=BOTH, expand=True)
        form.columnconfigure(1, weight=1)
        ttk.Label(
            form,
            text="Choose the local repository, default test command, and runtime model. The main action prepares the repo and opens the editable flow.",
            style="CardMuted.TLabel",
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))

        rows = [
            ("Project Directory", self.project_dir_var),
            ("Branch", self.branch_var),
            ("Origin URL (optional)", self.origin_url_var),
            ("Default Test Command", self.test_cmd_var),
        ]
        for row, (label, variable) in enumerate(rows, start=1):
            ttk.Label(form, text=label, style="Field.TLabel").grid(row=row, column=0, sticky=W, padx=(0, 12), pady=8)
            ttk.Entry(form, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=8)
            if label == "Project Directory":
                ttk.Button(form, text="Browse", command=self._choose_project_dir, style="Secondary.TButton").grid(row=row, column=2, padx=(8, 0), pady=8)

        runtime_card = ttk.LabelFrame(form, text="Execution Model", padding=12, style="Card.TLabelframe")
        runtime_card.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        runtime_card.columnconfigure(1, weight=1)
        ttk.Label(
            runtime_card,
            text="Pick a model the easy way. Type a full slug directly or compose a Codex slug from editable parts.",
            style="CardMuted.TLabel",
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))

        ttk.Label(runtime_card, text="Mode", style="Field.TLabel").grid(row=1, column=0, sticky=W, padx=(0, 12), pady=6)
        mode_row = ttk.Frame(runtime_card, style="Card.TFrame")
        mode_row.grid(row=1, column=1, columnspan=2, sticky=W, pady=6)
        ttk.Radiobutton(mode_row, text="Codex Builder", value=MODEL_MODE_CODEX, variable=self.model_mode_var, style="Card.TRadiobutton").pack(side=LEFT)
        ttk.Radiobutton(mode_row, text="Direct Slug", value=MODEL_MODE_SLUG, variable=self.model_mode_var, style="Card.TRadiobutton").pack(side=LEFT, padx=(12, 0))

        ttk.Label(runtime_card, text="Direct Slug", style="Field.TLabel").grid(row=2, column=0, sticky=W, padx=(0, 12), pady=6)
        self.direct_model_entry = ttk.Entry(runtime_card, textvariable=self.model_slug_input_var)
        self.direct_model_entry.grid(row=2, column=1, columnspan=2, sticky="ew", pady=6)

        ttk.Label(runtime_card, text="Codex Base Slug", style="Field.TLabel").grid(row=3, column=0, sticky=W, padx=(0, 12), pady=6)
        self.codex_base_entry = ttk.Entry(runtime_card, textvariable=self.codex_base_slug_var)
        self.codex_base_entry.grid(row=3, column=1, sticky="ew", pady=6)
        ttk.Label(runtime_card, text="Examples: gpt-5.4, gpt-5.1, codex-mini", style="CardMuted.TLabel").grid(
            row=3,
            column=2,
            sticky=W,
            padx=(12, 0),
            pady=6,
        )

        ttk.Label(runtime_card, text="Codex Variant", style="Field.TLabel").grid(row=4, column=0, sticky=W, padx=(0, 12), pady=6)
        self.codex_variant_entry = ttk.Entry(runtime_card, textvariable=self.codex_variant_slug_var)
        self.codex_variant_entry.grid(row=4, column=1, sticky="ew", pady=6)
        ttk.Label(runtime_card, text="Examples: codex, codex-max, latest", style="CardMuted.TLabel").grid(
            row=4,
            column=2,
            sticky=W,
            padx=(12, 0),
            pady=6,
        )

        ttk.Label(runtime_card, text="Resolved Slug", style="Field.TLabel").grid(row=5, column=0, sticky=W, padx=(0, 12), pady=6)
        ttk.Label(runtime_card, textvariable=self.model_var, style="Value.TLabel").grid(row=5, column=1, columnspan=2, sticky=W, pady=6)

        ttk.Label(runtime_card, text="Reasoning Effort", style="Field.TLabel").grid(row=6, column=0, sticky=W, padx=(0, 12), pady=6)
        ttk.Combobox(runtime_card, textvariable=self.effort_var, values=["low", "medium", "high", "xhigh"], state="readonly", width=20).grid(
            row=6,
            column=1,
            sticky=W,
            pady=6,
        )
        ttk.Label(
            runtime_card,
            text="The resolved slug is saved in project_config.json, so future model additions do not require UI updates.",
            style="CardMuted.TLabel",
            anchor="w",
        ).grid(row=7, column=0, columnspan=3, sticky="ew", pady=(4, 0))

        ttk.Label(form, text="Max Planned Steps", style="Field.TLabel").grid(row=6, column=0, sticky=W, padx=(0, 12), pady=8)
        ttk.Entry(form, textvariable=self.max_steps_var, width=10).grid(row=6, column=1, sticky=W, pady=8)

        assumptions = ttk.LabelFrame(form, text="What This Run Assumes", padding=12, style="Card.TLabelframe")
        assumptions.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(16, 0))
        for text in [
            "GitHub login and Codex CLI login already exist on this machine.",
            "Codex execution uses approval=never and sandbox=danger-full-access.",
            "Stage 1 creates `.venv` and ensures `.gitignore` covers common Python artifacts.",
            "Stage execution commits and pushes after each verified step when `origin` is configured.",
        ]:
            ttk.Label(assumptions, text=text, style="CardMuted.TLabel", anchor="w").pack(fill=X, pady=2)

        flow_overview = ttk.LabelFrame(form, text="Runtime Flow Chart", padding=12, style="Card.TLabelframe")
        flow_overview.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(16, 0))
        self.setup_flow_canvas = Canvas(flow_overview, background="#fffdf9", height=246, highlightthickness=0)
        self.setup_flow_canvas.pack(fill=X, expand=True)
        self.setup_flow_canvas.bind("<Configure>", lambda _event: self._draw_setup_flow_chart())
        ttk.Label(
            flow_overview,
            text="The selected model slug is reused for plan generation, step execution, and closeout.",
            style="CardMuted.TLabel",
            anchor="w",
        ).pack(fill=X, pady=(10, 0))

        setup_actions = ttk.Frame(form, style="Card.TFrame")
        setup_actions.grid(row=9, column=0, columnspan=3, sticky="w", pady=(18, 0))
        ttk.Button(setup_actions, text="Prepare Environment and Open Flow", command=self.prepare_environment, style="Primary.TButton").pack(side=LEFT)
        ttk.Button(setup_actions, text="Open Current Flow", command=self.open_selected_project, style="Secondary.TButton").pack(side=LEFT, padx=(8, 0))

    def _build_flow_stage(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent, style="App.TFrame")
        header.pack(fill=X, pady=(0, 12))
        ttk.Button(header, text="Back To Setup", command=lambda: self._show_stage("setup"), style="Quiet.TButton").pack(side=LEFT)
        ttk.Label(header, textvariable=self.current_project_label_var, style="Stage.TLabel").pack(side=LEFT, padx=(12, 0))
        ttk.Label(header, textvariable=self.current_step_label_var, style="StatusPill.TLabel", padding=(12, 8)).pack(side=RIGHT)

        prompt_frame = ttk.LabelFrame(parent, text="Prompt And Plan", padding=12, style="Card.TLabelframe")
        prompt_frame.pack(fill=X)
        ttk.Label(
            prompt_frame,
            text="Describe the goal in plain language. Generate the plan, adjust the flow if needed, then run the remaining steps.",
            style="CardMuted.TLabel",
            anchor="w",
        ).pack(fill=X, pady=(0, 8))
        self.prompt_text = ScrolledText(prompt_frame, height=5, wrap="word")
        self.prompt_text.pack(fill=X)
        self._configure_text_surface(self.prompt_text)

        prompt_actions = ttk.Frame(prompt_frame, style="Card.TFrame")
        prompt_actions.pack(fill=X, pady=(10, 0))
        ttk.Button(prompt_actions, text="Generate Plan With Codex", command=self.generate_plan, style="Primary.TButton").pack(side=LEFT)
        ttk.Button(prompt_actions, text="Save Edited Plan", command=self.save_plan, style="Secondary.TButton").pack(side=LEFT, padx=(8, 0))
        ttk.Button(prompt_actions, text="Reset Plan", command=self.reset_plan, style="Quiet.TButton").pack(side=LEFT, padx=(8, 0))
        ttk.Button(prompt_actions, text="Run Remaining Steps", command=self.run_plan, style="Primary.TButton").pack(side=LEFT, padx=(8, 0))
        ttk.Button(prompt_actions, text="Run Closeout", command=self.run_closeout, style="Secondary.TButton").pack(side=LEFT, padx=(8, 0))
        ttk.Button(prompt_actions, text="Stop After Current Step", command=self.stop_after_current_step, style="Quiet.TButton").pack(side=LEFT, padx=(8, 0))
        ttk.Button(prompt_actions, text="Reload Project", command=self.reload_current_project, style="Quiet.TButton").pack(side=LEFT, padx=(8, 0))
        ttk.Label(prompt_frame, textvariable=self.runtime_summary_var, style="CardMuted.TLabel", anchor="w").pack(fill=X, pady=(10, 0))

        split = ttk.Panedwindow(parent, orient="horizontal")
        split.pack(fill=BOTH, expand=True, pady=(12, 0))

        flow_panel = ttk.LabelFrame(split, text="Interactive Flow", padding=12, style="Card.TLabelframe")
        editor_panel = ttk.LabelFrame(split, text="Selected Step", padding=12, style="Card.TLabelframe")
        split.add(flow_panel, weight=60)
        split.add(editor_panel, weight=40)

        flow_canvas_wrap = ttk.Frame(flow_panel)
        flow_canvas_wrap.pack(fill=BOTH, expand=True)
        self.flow_canvas = Canvas(flow_canvas_wrap, background="#fffdf9", highlightthickness=0)
        flow_x = ttk.Scrollbar(flow_canvas_wrap, orient="horizontal", command=self.flow_canvas.xview)
        flow_y = ttk.Scrollbar(flow_canvas_wrap, orient="vertical", command=self.flow_canvas.yview)
        self.flow_canvas.configure(xscrollcommand=flow_x.set, yscrollcommand=flow_y.set)
        self.flow_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        flow_y.pack(side=RIGHT, fill=Y)
        flow_x.pack(fill=X)

        ttk.Label(
            flow_panel,
            text="Flow is editable for pending steps only. Each completed node represents a verified checkpoint with commit/push when available.",
            style="CardMuted.TLabel",
            anchor="w",
        ).pack(fill=X, pady=(10, 0))

        editor_panel.columnconfigure(1, weight=1)
        ttk.Label(
            editor_panel,
            text="Select a pending step in the flow to refine its title, Codex instruction, test command, and success criteria.",
            style="CardMuted.TLabel",
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(editor_panel, text="Step ID", style="Field.TLabel").grid(row=1, column=0, sticky=W, padx=(0, 10), pady=6)
        ttk.Label(editor_panel, textvariable=self.selected_step_id_var, style="Value.TLabel").grid(row=1, column=1, sticky=W, pady=6)
        ttk.Label(editor_panel, text="Status", style="Field.TLabel").grid(row=2, column=0, sticky=W, padx=(0, 10), pady=6)
        ttk.Label(editor_panel, textvariable=self.selected_step_status_var, style="Value.TLabel").grid(row=2, column=1, sticky=W, pady=6)

        ttk.Label(editor_panel, text="Title", style="Field.TLabel").grid(row=3, column=0, sticky=W, padx=(0, 10), pady=6)
        self.step_title_var = StringVar()
        self.step_title_entry = ttk.Entry(editor_panel, textvariable=self.step_title_var)
        self.step_title_entry.grid(row=3, column=1, sticky="ew", pady=6)

        ttk.Label(editor_panel, text="Test Command", style="Field.TLabel").grid(row=4, column=0, sticky=W, padx=(0, 10), pady=6)
        self.step_test_var = StringVar()
        self.step_test_entry = ttk.Entry(editor_panel, textvariable=self.step_test_var)
        self.step_test_entry.grid(row=4, column=1, sticky="ew", pady=6)

        ttk.Label(editor_panel, text="Display Description", style="Field.TLabel").grid(row=5, column=0, sticky="nw", padx=(0, 10), pady=6)
        self.step_description_text = ScrolledText(editor_panel, height=5, wrap="word")
        self.step_description_text.grid(row=5, column=1, sticky="ew", pady=6)
        self._configure_text_surface(self.step_description_text)

        ttk.Label(editor_panel, text="Codex Instruction", style="Field.TLabel").grid(row=6, column=0, sticky="nw", padx=(0, 10), pady=6)
        self.step_codex_text = ScrolledText(editor_panel, height=6, wrap="word")
        self.step_codex_text.grid(row=6, column=1, sticky="ew", pady=6)
        self._configure_text_surface(self.step_codex_text)

        ttk.Label(editor_panel, text="Success Criteria", style="Field.TLabel").grid(row=7, column=0, sticky="nw", padx=(0, 10), pady=6)
        self.step_success_text = ScrolledText(editor_panel, height=4, wrap="word")
        self.step_success_text.grid(row=7, column=1, sticky="ew", pady=6)
        self._configure_text_surface(self.step_success_text)

        actions = ttk.Frame(editor_panel, style="Card.TFrame")
        actions.grid(row=8, column=0, columnspan=2, sticky="w", pady=(14, 0))
        ttk.Button(actions, text="Save Step", command=self.save_selected_step, style="Primary.TButton").pack(side=LEFT)
        ttk.Button(actions, text="Add Step", command=self.add_step_after_selection, style="Secondary.TButton").pack(side=LEFT, padx=(8, 0))
        ttk.Button(actions, text="Delete Step", command=self.delete_selected_step, style="Quiet.TButton").pack(side=LEFT, padx=(8, 0))
        ttk.Button(actions, text="Move Up", command=lambda: self.move_selected_step(-1), style="Quiet.TButton").pack(side=LEFT, padx=(8, 0))
        ttk.Button(actions, text="Move Down", command=lambda: self.move_selected_step(1), style="Quiet.TButton").pack(side=LEFT, padx=(8, 0))
        ttk.Button(actions, text="Clear Selection", command=self.clear_step_selection, style="Quiet.TButton").pack(side=LEFT, padx=(8, 0))

    def _build_bottom_panel(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=BOTH, expand=True)

        activity_tab = ttk.Frame(notebook, style="Card.TFrame")
        snapshot_tab = ttk.Frame(notebook, style="Card.TFrame")
        notebook.add(activity_tab, text="Activity")
        notebook.add(snapshot_tab, text="Snapshot")

        self.log_text = ScrolledText(activity_tab, height=12, wrap="word")
        self.log_text.pack(fill=BOTH, expand=True)
        self._configure_text_surface(self.log_text, background="#fffaf6")
        self.snapshot_text = ScrolledText(snapshot_tab, height=12, wrap="word")
        self.snapshot_text.pack(fill=BOTH, expand=True)
        self._configure_text_surface(self.snapshot_text, background="#fffaf6")

    def _configure_text_surface(self, widget: ScrolledText, background: str = "#fffdf9") -> None:
        widget.configure(
            background=background,
            foreground="#22313a",
            borderwidth=0,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#e3d8cb",
            highlightcolor="#d0b9a9",
            insertbackground="#22313a",
            padx=10,
            pady=10,
            font=("Malgun Gothic", 10),
            selectbackground="#f1ddcf",
            selectforeground="#22313a",
        )

    def _current_model_selection(self) -> ModelSelection:
        return ModelSelection(
            mode=self.model_mode_var.get().strip(),
            direct_slug=self.model_slug_input_var.get().strip(),
            codex_base_slug=self.codex_base_slug_var.get().strip(),
            codex_variant_slug=self.codex_variant_slug_var.get().strip(),
            effort=self.effort_var.get().strip(),
        )

    def _load_runtime_inputs(self, runtime: RuntimeOptions) -> None:
        selection = model_selection_from_runtime(runtime)
        self.model_mode_var.set(selection.normalized_mode())
        self.model_slug_input_var.set(selection.direct_slug)
        self.codex_base_slug_var.set(selection.codex_base_slug)
        self.codex_variant_slug_var.set(selection.codex_variant_slug)
        self.effort_var.set(selection.normalized_effort())
        self._sync_runtime_model_ui()

    def _on_runtime_model_changed(self, *_args: object) -> None:
        self._sync_runtime_model_ui()

    def _sync_runtime_model_ui(self) -> None:
        mode = normalize_model_mode(self.model_mode_var.get())
        if self.model_mode_var.get() != mode:
            self.model_mode_var.set(mode)
            return
        direct_state = "normal" if mode == MODEL_MODE_SLUG else "disabled"
        codex_state = "normal" if mode == MODEL_MODE_CODEX else "disabled"
        if hasattr(self, "direct_model_entry"):
            self.direct_model_entry.configure(state=direct_state)
        if hasattr(self, "codex_base_entry"):
            self.codex_base_entry.configure(state=codex_state)
        if hasattr(self, "codex_variant_entry"):
            self.codex_variant_entry.configure(state=codex_state)
        try:
            selection = self._current_model_selection()
            resolved_slug = selection.resolved_slug()
            summary = selection.summary()
        except ValueError as exc:
            resolved_slug = ""
            summary = f"Model slug is incomplete: {exc}"
        self.model_var.set(resolved_slug)
        self.runtime_summary_var.set(summary)
        if hasattr(self, "setup_flow_canvas"):
            self._draw_setup_flow_chart()

    def _draw_setup_flow_chart(self) -> None:
        self.setup_flow_canvas.delete("all")
        width = max(self.setup_flow_canvas.winfo_width(), 720)
        box_width = 204
        box_height = 74
        margin_x = 24
        margin_y = 20
        gap_x = 24
        gap_y = 48
        nodes = [
            ("1. Setup", "Prepare repo, .venv, and safe revision."),
            ("2. Model", self.model_var.get().strip() or "Resolve the execution slug."),
            ("3. Plan", "Generate the editable execution plan."),
            ("4. Review", "Edit flow nodes, tests, and Codex instructions."),
            ("5. Execute", "Run each pending step with verification."),
            ("6. Closeout", "Finalize reports, commit, and optional push."),
        ]
        positions: list[tuple[float, float, float, float]] = []
        for index, (title, body) in enumerate(nodes):
            row = index // 3
            col = index % 3
            x1 = margin_x + col * (box_width + gap_x)
            y1 = margin_y + row * (box_height + gap_y)
            x2 = x1 + box_width
            y2 = y1 + box_height
            positions.append((x1, y1, x2, y2))
            fill = "#f8e8df" if index == 1 else "#fffaf6"
            outline = "#cf8b6c" if index == 1 else "#e6d9cc"
            self.setup_flow_canvas.create_rectangle(x1 + 4, y1 + 5, x2 + 4, y2 + 5, fill="#efe4d8", outline="#efe4d8", width=0)
            self.setup_flow_canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=2)
            self.setup_flow_canvas.create_text(
                x1 + 12,
                y1 + 18,
                text=title,
                anchor="w",
                fill="#22313a",
                font=("Malgun Gothic", 11, "bold"),
            )
            self.setup_flow_canvas.create_text(
                x1 + 12,
                y1 + 44,
                text=textwrap.shorten(body, width=34, placeholder="..."),
                anchor="w",
                fill="#6d7b83",
                font=("Malgun Gothic", 9),
            )
        for index in range(len(positions) - 1):
            x1, y1, x2, y2 = positions[index]
            next_x1, next_y1, next_x2, _next_y2 = positions[index + 1]
            if y1 == next_y1:
                center_y = y1 + box_height / 2
                self.setup_flow_canvas.create_line(x2 + 6, center_y, next_x1 - 6, center_y, fill="#d1bcac", width=3, arrow="last")
                continue
            current_center_x = (x1 + x2) / 2
            next_center_x = (next_x1 + next_x2) / 2
            mid_y = y2 + gap_y / 2
            self.setup_flow_canvas.create_line(
                current_center_x,
                y2 + 4,
                current_center_x,
                mid_y,
                next_center_x,
                mid_y,
                next_center_x,
                next_y1 - 6,
                fill="#d1bcac",
                width=3,
                arrow="last",
                smooth=False,
            )
        total_width = min(width, margin_x * 2 + box_width * 3 + gap_x * 2)
        total_height = margin_y * 2 + box_height * 2 + gap_y
        self.setup_flow_canvas.configure(scrollregion=(0, 0, total_width, total_height))

    def _show_stage(self, name: str) -> None:
        for child in self.stage_container.winfo_children():
            child.pack_forget()
        if name == "flow":
            self.stage_title_var.set("Plan And Run")
            self.stage_hint_var.set("Turn the request into a step-by-step flow, then execute and close out the project safely.")
            self.flow_stage.pack(fill=BOTH, expand=True)
            return
        self.stage_title_var.set("Workspace Setup")
        self.stage_hint_var.set("Choose a local repository and runtime model, then prepare the workspace.")
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
        selection = self._current_model_selection()
        effort = validate_reasoning_effort(selection.effort or "medium")
        return RuntimeOptions(
            model=selection.resolved_slug(),
            model_selection_mode=selection.normalized_mode(),
            model_slug_input=selection.direct_slug.strip(),
            codex_base_slug=selection.codex_base_slug.strip(),
            codex_variant_slug=selection.codex_variant_slug.strip(),
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
                "model": project.runtime.model,
                "model_selection_mode": project.runtime.model_selection_mode,
                "reasoning_effort": project.runtime.effort,
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
        self._load_runtime_inputs(project.runtime)
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
        self._load_runtime_inputs(project.runtime)
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
            step_id=f"ST{len(self.current_plan.steps) + 1}",
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
            "completed": ("#e6f4ec", "#28533b"),
            "running": ("#eaf2fb", "#35526b"),
            "paused": ("#fbf0dd", "#8a5a1d"),
            "failed": ("#fbe7e3", "#8a4035"),
            "pending": ("#fffaf6", "#22313a"),
            "not_started": ("#fffaf6", "#22313a"),
        }
        nodes: list[dict[str, str]] = [
            {
                "kind": "step",
                "node_id": step.step_id,
                "title": step.title,
                "body": step.display_description or step.test_command or "No step summary.",
                "status": step.status,
            }
            for step in steps
        ]
        nodes.append(
            {
                "kind": "closeout",
                "node_id": "CLOSEOUT",
                "title": "Project closeout",
                "body": self.current_plan.closeout_notes or "Finalize reports, verify final state, and capture the closeout commit.",
                "status": self.current_plan.closeout_status or "not_started",
            }
        )
        positions: list[tuple[float, float, float, float]] = []

        for index, node in enumerate(nodes):
            row = index // per_row
            col = index % per_row
            x1 = margin_x + col * (box_width + gap_x)
            y1 = margin_y + row * (box_height + gap_y)
            x2 = x1 + box_width
            y2 = y1 + box_height
            positions.append((x1, y1, x2, y2))
            status = node["status"] if node["status"] in colors else "pending"
            fill, text_fill = colors[status]
            selected = node["kind"] == "step" and node["node_id"] == self.selected_step_id
            outline = "#c9795d" if selected else "#e6d9cc"
            width = 3 if selected else 2
            tags = ("step", node["node_id"])
            self.flow_canvas.create_rectangle(x1 + 5, y1 + 6, x2 + 5, y2 + 6, fill="#efe4d8", outline="#efe4d8", width=0)
            self.flow_canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=width, tags=tags)
            self.flow_canvas.create_text(x1 + 14, y1 + 18, text=node["node_id"], anchor="w", fill=text_fill, font=("Malgun Gothic", 12, "bold"), tags=tags)
            self.flow_canvas.create_text(
                x1 + 14,
                y1 + 46,
                text=textwrap.shorten(node["title"], width=38, placeholder="..."),
                anchor="w",
                fill=text_fill,
                font=("Malgun Gothic", 11, "bold"),
                tags=tags,
            )
            self.flow_canvas.create_text(
                x1 + 14,
                y1 + 74,
                text=textwrap.shorten(node["body"], width=42, placeholder="..."),
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
            if node["kind"] == "step":
                self.flow_canvas.tag_bind(node["node_id"], "<Button-1>", lambda _event, step_id=node["node_id"]: self.select_step(step_id))

        for index in range(len(positions) - 1):
            x1, y1, x2, y2 = positions[index]
            next_x1, next_y1, next_x2, _next_y2 = positions[index + 1]
            if y1 == next_y1:
                center_y = y1 + box_height / 2
                self.flow_canvas.create_line(x2 + 6, center_y, next_x1 - 6, center_y, fill="#d1bcac", width=4, arrow="last", smooth=True)
                continue
            current_center_x = (x1 + x2) / 2
            next_center_x = (next_x1 + next_x2) / 2
            mid_y = y2 + gap_y / 2
            self.flow_canvas.create_line(
                current_center_x,
                y2 + 4,
                current_center_x,
                mid_y,
                next_center_x,
                mid_y,
                next_center_x,
                next_y1 - 6,
                fill="#d1bcac",
                width=4,
                arrow="last",
                smooth=True,
            )

        rows = (len(nodes) + per_row - 1) // per_row
        width = margin_x * 2 + per_row * box_width + max(0, per_row - 1) * gap_x
        height = margin_y * 2 + rows * box_height + max(0, rows - 1) * gap_y
        self.flow_canvas.configure(scrollregion=(0, 0, width, height))


def main() -> int:
    root = Tk()
    app = CodexAutoGUI(root)
    app._append_log("GUI ready")
    root.mainloop()
    return 0
