from __future__ import annotations

from copy import deepcopy
import json
import os
import queue
import textwrap
import threading
import traceback
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, W, X, Y, Canvas, StringVar, Tk, filedialog, messagebox
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from .model_selection import DEFAULT_MODEL_PRESET_ID, MODEL_PRESETS, model_preset_by_id, model_preset_from_runtime
from .models import ExecutionPlanState, ExecutionStep, ProjectContext, RuntimeOptions
from .orchestrator import Orchestrator
from .utils import read_jsonl_tail


DEFAULT_GUI_WORKSPACE_DIRNAME = ".codex-auto-workspace"
GITHUB_CONNECTION_EXISTING = "existing"
GITHUB_CONNECTION_MANUAL = "manual"
GITHUB_CONNECTION_NONE = "none"
CUSTOM_MODEL_PRESET_ID = "__custom__"


def _default_gui_workspace_root() -> Path:
    explicit = os.environ.get("CODEX_AUTO_GUI_WORKSPACE")
    if explicit:
        return Path(explicit).expanduser().resolve()
    legacy = (Path.cwd() / DEFAULT_GUI_WORKSPACE_DIRNAME).resolve()
    if legacy.exists():
        return legacy
    return (Path.home() / DEFAULT_GUI_WORKSPACE_DIRNAME).resolve()


def _project_initials(name: str) -> str:
    compact = " ".join(name.split()).strip()
    if not compact:
        return "PR"
    tokens = [token for token in compact.replace("_", " ").replace("-", " ").split() if token]
    if len(tokens) >= 2:
        return (tokens[0][0] + tokens[1][0]).upper()[:2]
    letters = "".join(char for char in compact if char.isalnum())
    if not letters:
        return "PR"
    return letters[:2].upper()


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
        self._log_buffer: list[str] = []
        self._latest_snapshot_text = ""

        self.workspace_root = _default_gui_workspace_root()
        self.project_name_var = StringVar()
        self.project_dir_var = StringVar()
        self.branch_var = StringVar(value="main")
        self.origin_url_var = StringVar()
        self.github_connection_var = StringVar(value=GITHUB_CONNECTION_EXISTING)
        self.model_preset_var = StringVar(value=DEFAULT_MODEL_PRESET_ID)
        self.model_var = StringVar(value=model_preset_by_id(DEFAULT_MODEL_PRESET_ID).model)
        self.runtime_summary_var = StringVar(value="")
        self.test_cmd_var = StringVar(value="python -m pytest")
        self.max_steps_var = StringVar(value="5")
        self.status_var = StringVar(value="Ready")
        self.setup_form_title_var = StringVar(value="Create Managed Project")
        self.setup_form_hint_var = StringVar(value="Pick a directory, give it a simple name, choose the GitHub link mode, then use Next to open the flow.")
        self.primary_action_var = StringVar(value="Create Project")
        self.next_action_var = StringVar(value="Next: Create Project And Open Flow")
        self.current_project_label_var = StringVar(value="No project selected")
        self.current_step_label_var = StringVar(value="No plan loaded")
        self.selected_step_id_var = StringVar(value="")
        self.selected_step_status_var = StringVar(value="")

        self.project_rows: dict[str, ProjectContext] = {}
        self.selected_project_id: str | None = None
        self.current_project: ProjectContext | None = None
        self.current_plan = ExecutionPlanState()
        self.selected_step_id: str | None = None
        self.flow_node_tags: dict[str, list[int]] = {}
        self._orchestrator_instance: Orchestrator | None = None
        self._orchestrator_root: Path | None = None
        self._custom_model_choice: tuple[str, str] | None = None
        self.model_preset_var.trace_add("write", self._on_runtime_model_changed)
        self.github_connection_var.trace_add("write", self._on_github_connection_changed)

        self._configure_style()
        self._build_layout()
        self._load_runtime_inputs(RuntimeOptions())
        self._sync_github_mode_ui()
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
        ink = "#22313a"
        soft_ink = "#6d7b83"
        border = "#e3d8cb"
        accent = "#c9795d"
        accent_active = "#b6664b"
        accent_soft = "#f6e2d7"
        selected_bg = "#f8e8df"
        style.configure("App.TFrame", background=app_bg)
        style.configure("Toolbar.TFrame", background=app_bg)
        style.configure("Card.TFrame", background=panel_bg)
        style.configure("ProjectCard.TFrame", background=surface_bg, borderwidth=1, relief="solid", bordercolor=border)
        style.configure("ProjectCardSelected.TFrame", background=selected_bg, borderwidth=2, relief="solid", bordercolor=accent)
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
        style.configure("Muted.TLabel", background=app_bg, foreground=soft_ink, font=("Malgun Gothic", 10))
        style.configure("CardMuted.TLabel", background=panel_bg, foreground=soft_ink, font=("Malgun Gothic", 10))
        style.configure("ProjectTitle.TLabel", background=surface_bg, foreground=ink, font=("Malgun Gothic", 11, "bold"))
        style.configure("ProjectTitleSelected.TLabel", background=selected_bg, foreground=ink, font=("Malgun Gothic", 11, "bold"))
        style.configure("ProjectMeta.TLabel", background=surface_bg, foreground=soft_ink, font=("Malgun Gothic", 9))
        style.configure("ProjectMetaSelected.TLabel", background=selected_bg, foreground=soft_ink, font=("Malgun Gothic", 9))
        style.configure("Field.TLabel", background=panel_bg, foreground=ink, font=("Malgun Gothic", 10, "bold"))
        style.configure("Value.TLabel", background=panel_bg, foreground=ink, font=("Malgun Gothic", 10))
        style.configure("Section.TLabel", background=panel_bg, foreground=ink, font=("Malgun Gothic", 16, "bold"))
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

        self.stage_container = ttk.Frame(root_frame, style="App.TFrame")
        self.stage_container.pack(fill=BOTH, expand=True)

        self.setup_stage = ttk.Frame(self.stage_container, style="App.TFrame")
        self.flow_stage = ttk.Frame(self.stage_container, style="App.TFrame")
        self._build_setup_stage(self.setup_stage)
        self._build_flow_stage(self.flow_stage)

    def _build_setup_stage(self, parent: ttk.Frame) -> None:
        split = ttk.Panedwindow(parent, orient="horizontal")
        split.pack(fill=BOTH, expand=True)

        left = ttk.LabelFrame(split, text="Managed Projects", padding=12, style="Card.TLabelframe")
        self.setup_detail_card = ttk.LabelFrame(split, text="Choose Next Step", padding=12, style="Card.TLabelframe")
        split.add(left, weight=44)
        split.add(self.setup_detail_card, weight=56)

        ttk.Label(
            left,
            text="Click an existing project to open its flow, or use Create New to register another directory.",
            style="CardMuted.TLabel",
            anchor="w",
        ).pack(fill=X, pady=(0, 10))

        project_actions = ttk.Frame(left, style="Card.TFrame")
        project_actions.pack(fill=X, pady=(10, 0))
        ttk.Button(project_actions, text="Create New", command=self.start_new_project, style="Primary.TButton").pack(side=LEFT)
        ttk.Button(project_actions, text="Edit Selected", command=self.load_selected_project_into_form, style="Secondary.TButton").pack(side=LEFT, padx=(8, 0))
        ttk.Button(project_actions, text="Refresh", command=self.refresh_projects, style="Secondary.TButton").pack(side=LEFT, padx=(8, 0))

        browser_wrap = ttk.Frame(left, style="Card.TFrame")
        browser_wrap.pack(fill=BOTH, expand=True, pady=(12, 0))
        self.project_browser_canvas = Canvas(browser_wrap, background="#fffaf5", highlightthickness=0)
        browser_scroll = ttk.Scrollbar(browser_wrap, orient="vertical", command=self.project_browser_canvas.yview)
        self.project_browser_canvas.configure(yscrollcommand=browser_scroll.set)
        self.project_browser_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        browser_scroll.pack(side=RIGHT, fill=Y)
        self.project_browser_frame = ttk.Frame(self.project_browser_canvas, style="Card.TFrame")
        self.project_browser_window = self.project_browser_canvas.create_window((0, 0), window=self.project_browser_frame, anchor="nw")
        self.project_browser_frame.bind(
            "<Configure>",
            lambda _event: self.project_browser_canvas.configure(scrollregion=self.project_browser_canvas.bbox("all")),
        )
        self.project_browser_canvas.bind("<Configure>", self._on_project_browser_resized)

        self.project_summary_text = ScrolledText(left, height=10, wrap="word")
        self.project_summary_text.pack(fill=BOTH, expand=False, pady=(12, 0))
        self._configure_text_surface(self.project_summary_text)
        self.project_summary_text.insert("1.0", "Click a managed project to open its flow, or use Create New to register a new one.")

        self.setup_detail_container = ttk.Frame(self.setup_detail_card, style="Card.TFrame")
        self.setup_detail_container.pack(fill=BOTH, expand=True)

        self.setup_empty_panel = ttk.Frame(self.setup_detail_container, style="Card.TFrame")
        ttk.Label(self.setup_empty_panel, text="Projects First", style="Section.TLabel", anchor="w").pack(fill=X)
        ttk.Label(
            self.setup_empty_panel,
            text="The create form stays hidden until you press Create New. Existing projects open the next stage directly when clicked.",
            style="CardMuted.TLabel",
            anchor="w",
            justify=LEFT,
            wraplength=560,
        ).pack(fill=X, pady=(6, 0))
        ttk.Button(self.setup_empty_panel, text="Create New Project", command=self.start_new_project, style="Primary.TButton").pack(anchor="w", pady=(18, 0))

        form = ttk.Frame(self.setup_detail_container, style="Card.TFrame")
        self.setup_form_panel = form
        form.pack(fill=BOTH, expand=True)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, textvariable=self.setup_form_title_var, style="Section.TLabel", anchor="w").grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
        )
        ttk.Label(
            form,
            textvariable=self.setup_form_hint_var,
            style="CardMuted.TLabel",
            anchor="w",
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 14))

        ttk.Label(form, text="Project Name", style="Field.TLabel").grid(row=2, column=0, sticky=W, padx=(0, 12), pady=8)
        ttk.Entry(form, textvariable=self.project_name_var).grid(row=2, column=1, columnspan=2, sticky="ew", pady=8)

        ttk.Label(form, text="Working Directory", style="Field.TLabel").grid(row=3, column=0, sticky=W, padx=(0, 12), pady=8)
        ttk.Entry(form, textvariable=self.project_dir_var).grid(row=3, column=1, sticky="ew", pady=8)
        ttk.Button(form, text="Browse", command=self._choose_project_dir, style="Secondary.TButton").grid(row=3, column=2, padx=(8, 0), pady=8)

        github_card = ttk.LabelFrame(form, text="GitHub Connection", padding=12, style="Card.TLabelframe")
        github_card.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Label(
            github_card,
            text="Choose how this project should connect to GitHub. Only the selected path is shown.",
            style="CardMuted.TLabel",
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        ttk.Radiobutton(
            github_card,
            text="Use existing origin in this folder",
            value=GITHUB_CONNECTION_EXISTING,
            variable=self.github_connection_var,
            style="Card.TRadiobutton",
        ).grid(row=1, column=0, sticky=W, pady=4)
        ttk.Radiobutton(
            github_card,
            text="Paste a GitHub repository URL",
            value=GITHUB_CONNECTION_MANUAL,
            variable=self.github_connection_var,
            style="Card.TRadiobutton",
        ).grid(row=2, column=0, sticky=W, pady=4)
        ttk.Radiobutton(
            github_card,
            text="Do not connect GitHub yet",
            value=GITHUB_CONNECTION_NONE,
            variable=self.github_connection_var,
            style="Card.TRadiobutton",
        ).grid(row=3, column=0, sticky=W, pady=4)
        self.origin_url_label = ttk.Label(github_card, text="GitHub URL", style="Field.TLabel")
        self.origin_url_label.grid(row=4, column=0, sticky=W, padx=(0, 12), pady=(10, 6))
        self.origin_url_entry = ttk.Entry(github_card, textvariable=self.origin_url_var)
        self.origin_url_entry.grid(row=5, column=0, sticky="ew", pady=(0, 2))
        github_card.columnconfigure(0, weight=1)

        ttk.Label(form, text="Verification Command", style="Field.TLabel").grid(row=5, column=0, sticky=W, padx=(0, 12), pady=8)
        ttk.Entry(form, textvariable=self.test_cmd_var).grid(row=5, column=1, columnspan=2, sticky="ew", pady=8)

        runtime_card = ttk.LabelFrame(form, text="Execution Model", padding=12, style="Card.TLabelframe")
        runtime_card.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Label(
            runtime_card,
            text="Choose one working preset. The UI no longer builds custom Codex slug combinations that may not exist.",
            style="CardMuted.TLabel",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.model_options_frame = ttk.Frame(runtime_card, style="Card.TFrame")
        self.model_options_frame.grid(row=1, column=0, sticky="ew")
        runtime_card.columnconfigure(0, weight=1)
        self._build_model_options()
        self.custom_model_notice = ttk.Label(runtime_card, text="", style="CardMuted.TLabel", anchor="w")
        self.custom_model_notice.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(runtime_card, textvariable=self.runtime_summary_var, style="Value.TLabel", anchor="w").grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(8, 0),
        )

        setup_actions = ttk.Frame(form, style="Card.TFrame")
        setup_actions.grid(row=7, column=0, columnspan=3, sticky="w", pady=(18, 0))
        ttk.Button(setup_actions, textvariable=self.primary_action_var, command=self.save_project_setup, style="Secondary.TButton").pack(side=LEFT)
        ttk.Button(setup_actions, textvariable=self.next_action_var, command=self.advance_from_setup, style="Primary.TButton").pack(side=LEFT, padx=(8, 0))
        ttk.Button(setup_actions, text="Cancel", command=self.close_setup_form, style="Quiet.TButton").pack(side=LEFT, padx=(8, 0))

        self._show_setup_detail("welcome")

    def _build_flow_stage(self, parent: ttk.Frame) -> None:
        prompt_frame = ttk.LabelFrame(parent, text="Prompt And Plan", padding=12, style="Card.TLabelframe")
        prompt_frame.pack(fill=X)
        top_actions = ttk.Frame(prompt_frame, style="Card.TFrame")
        top_actions.pack(fill=X, pady=(0, 8))
        ttk.Button(top_actions, text="Back To Projects", command=lambda: self._show_stage("setup"), style="Quiet.TButton").pack(side=LEFT)
        ttk.Label(top_actions, textvariable=self.status_var, style="StatusPill.TLabel", padding=(12, 8)).pack(side=RIGHT)
        ttk.Label(prompt_frame, textvariable=self.current_project_label_var, style="Section.TLabel", anchor="w").pack(fill=X)
        ttk.Label(prompt_frame, textvariable=self.current_step_label_var, style="CardMuted.TLabel", anchor="w").pack(fill=X, pady=(4, 10))
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

    def _build_model_options(self) -> None:
        for child in self.model_options_frame.winfo_children():
            child.destroy()
        for row, preset in enumerate(MODEL_PRESETS):
            option = ttk.Frame(self.model_options_frame, style="Card.TFrame")
            option.grid(row=row, column=0, sticky="ew", pady=(0, 8))
            ttk.Radiobutton(
                option,
                text=f"{preset.label}  ({preset.model})",
                value=preset.preset_id,
                variable=self.model_preset_var,
                style="Card.TRadiobutton",
            ).pack(anchor="w")
            ttk.Label(option, text=preset.description, style="CardMuted.TLabel", anchor="w").pack(fill=X, padx=(26, 0), pady=(2, 0))
        self.custom_model_row = ttk.Frame(self.model_options_frame, style="Card.TFrame")
        self.custom_model_row.grid(row=len(MODEL_PRESETS), column=0, sticky="ew")
        self.custom_model_radio = ttk.Radiobutton(
            self.custom_model_row,
            text="Saved Custom Model",
            value=CUSTOM_MODEL_PRESET_ID,
            variable=self.model_preset_var,
            style="Card.TRadiobutton",
        )
        self.custom_model_radio.pack(anchor="w")
        self.custom_model_label = ttk.Label(self.custom_model_row, text="", style="CardMuted.TLabel", anchor="w")
        self.custom_model_label.pack(fill=X, padx=(26, 0), pady=(2, 0))
        self.custom_model_row.grid_remove()

    def _selected_runtime_model(self) -> tuple[str, str, str]:
        preset_id = self.model_preset_var.get().strip()
        if preset_id == CUSTOM_MODEL_PRESET_ID and self._custom_model_choice is not None:
            model, effort = self._custom_model_choice
            return "", model, effort
        preset = model_preset_by_id(preset_id or DEFAULT_MODEL_PRESET_ID)
        return preset.preset_id, preset.model, preset.effort

    def _load_runtime_inputs(self, runtime: RuntimeOptions) -> None:
        preset = model_preset_from_runtime(runtime)
        if preset is not None:
            self._custom_model_choice = None
            self.model_preset_var.set(preset.preset_id)
        else:
            model = runtime.model.strip() or model_preset_by_id(DEFAULT_MODEL_PRESET_ID).model
            effort = runtime.effort.strip() or "high"
            self._custom_model_choice = (model, effort)
            self.model_preset_var.set(CUSTOM_MODEL_PRESET_ID)
        self._sync_runtime_model_ui()

    def _on_runtime_model_changed(self, *_args: object) -> None:
        self._sync_runtime_model_ui()

    def _sync_runtime_model_ui(self) -> None:
        preset_id, model, effort = self._selected_runtime_model()
        self.model_var.set(model)
        if preset_id == CUSTOM_MODEL_PRESET_ID or not preset_id:
            self.runtime_summary_var.set(f"Saved custom model {model} | reasoning {effort}")
        else:
            preset = model_preset_by_id(preset_id)
            self.runtime_summary_var.set(preset.summary())
        if self._custom_model_choice is not None and hasattr(self, "custom_model_row"):
            custom_model, custom_effort = self._custom_model_choice
            self.custom_model_label.configure(text=f"{custom_model} | reasoning {custom_effort}")
            self.custom_model_notice.configure(text="A previously saved custom model is still available for this project.")
            self.custom_model_row.grid()
        elif hasattr(self, "custom_model_row"):
            if self.model_preset_var.get() == CUSTOM_MODEL_PRESET_ID:
                self.model_preset_var.set(DEFAULT_MODEL_PRESET_ID)
            self.custom_model_notice.configure(text="")
            self.custom_model_row.grid_remove()

    def _show_stage(self, name: str) -> None:
        for child in self.stage_container.winfo_children():
            child.pack_forget()
        if name == "flow":
            self.flow_stage.pack(fill=BOTH, expand=True)
            return
        self.setup_stage.pack(fill=BOTH, expand=True)

    def _on_github_connection_changed(self, *_args: object) -> None:
        self._sync_github_mode_ui()

    def _sync_github_mode_ui(self) -> None:
        visible = self.github_connection_var.get().strip() == GITHUB_CONNECTION_MANUAL
        if hasattr(self, "origin_url_label"):
            if visible:
                self.origin_url_label.grid()
                self.origin_url_entry.grid()
            else:
                self.origin_url_label.grid_remove()
                self.origin_url_entry.grid_remove()

    def _build_project_card(self, parent: ttk.Frame, project: ProjectContext, selected: bool) -> None:
        frame_style = "ProjectCardSelected.TFrame" if selected else "ProjectCard.TFrame"
        title_style = "ProjectTitleSelected.TLabel" if selected else "ProjectTitle.TLabel"
        meta_style = "ProjectMetaSelected.TLabel" if selected else "ProjectMeta.TLabel"
        card = ttk.Frame(parent, style=frame_style, padding=12)
        card.pack(fill=X, pady=(0, 10))
        icon_bg = "#f8e8df" if selected else "#fffdf9"
        icon = Canvas(card, width=58, height=46, background=icon_bg, highlightthickness=0)
        icon.pack(side=LEFT, padx=(0, 12))
        icon.create_rectangle(8, 16, 50, 36, fill="#efc39f", outline="#d49062", width=1)
        icon.create_polygon(8, 16, 18, 10, 32, 10, 38, 16, fill="#f4d7bd", outline="#d49062", width=1)
        icon.create_text(29, 26, text=_project_initials(project.metadata.display_name or project.metadata.slug), fill="#7b462f", font=("Malgun Gothic", 9, "bold"))

        body = ttk.Frame(card, style=frame_style)
        body.pack(side=LEFT, fill=BOTH, expand=True)
        ttk.Label(body, text=project.metadata.display_name or project.metadata.slug, style=title_style, anchor="w").pack(fill=X)
        ttk.Label(body, text=project.metadata.current_status, style=meta_style, anchor="w").pack(fill=X, pady=(2, 0))
        ttk.Label(body, text=str(project.metadata.repo_path), style=meta_style, anchor="w").pack(fill=X, pady=(2, 0))
        detail = project.metadata.origin_url or f"Branch {project.metadata.branch}"
        ttk.Label(body, text=detail, style=meta_style, anchor="w").pack(fill=X, pady=(2, 0))

        callback = lambda _event, repo_id=project.metadata.repo_id: self._select_project_card(repo_id)
        self._bind_click_recursive(card, callback)

    def _bind_click_recursive(self, widget: object, callback: object) -> None:
        if hasattr(widget, "bind"):
            widget.bind("<Button-1>", callback)
        if hasattr(widget, "winfo_children"):
            for child in widget.winfo_children():
                self._bind_click_recursive(child, callback)

    def _on_project_browser_resized(self, event: object) -> None:
        if hasattr(self, "project_browser_canvas") and hasattr(self, "project_browser_window"):
            width = getattr(event, "width", None)
            if isinstance(width, int):
                self.project_browser_canvas.itemconfigure(self.project_browser_window, width=width)

    def _select_project_card(self, repo_id: str) -> None:
        self.selected_project_id = repo_id
        project = self._selected_project()
        if project is None:
            return
        self._populate_project_form(project)
        self.project_summary_text.delete("1.0", END)
        self.project_summary_text.insert("1.0", self._project_summary(project))
        self._render_project_list(list(self.project_rows.values()))

    def _populate_project_form(self, project: ProjectContext) -> None:
        self.project_name_var.set(project.metadata.display_name or project.metadata.slug)
        self.project_dir_var.set(str(project.metadata.repo_path))
        self.branch_var.set(project.metadata.branch)
        self.origin_url_var.set(project.metadata.origin_url or "")
        self.github_connection_var.set(GITHUB_CONNECTION_MANUAL if project.metadata.origin_url else GITHUB_CONNECTION_EXISTING)
        self._load_runtime_inputs(project.runtime)
        self.test_cmd_var.set(project.runtime.test_cmd)
        self.max_steps_var.set(str(max(project.runtime.max_blocks, 1)))
        self.setup_form_title_var.set("Project Settings")
        self.setup_form_hint_var.set("Adjust the saved name, directory, GitHub link mode, or runtime preset, then use Next to reopen the flow.")
        self.primary_action_var.set("Save Project")
        self.next_action_var.set("Next: Save And Open Flow")

    def start_new_project(self) -> None:
        self.selected_project_id = None
        self.project_name_var.set("")
        self.project_dir_var.set("")
        self.branch_var.set("main")
        self.origin_url_var.set("")
        self.github_connection_var.set(GITHUB_CONNECTION_EXISTING)
        self.test_cmd_var.set("python -m pytest")
        self.max_steps_var.set("5")
        self._custom_model_choice = None
        self.model_preset_var.set(DEFAULT_MODEL_PRESET_ID)
        self.setup_form_title_var.set("Create Managed Project")
        self.setup_form_hint_var.set("Pick a directory, give it a simple name, choose the GitHub link mode, then use Next to open the flow.")
        self.primary_action_var.set("Create Project")
        self.next_action_var.set("Next: Create Project And Open Flow")
        self.project_summary_text.delete("1.0", END)
        self.project_summary_text.insert("1.0", "Create a new managed project or select one from the list.")
        self._render_project_list(list(self.project_rows.values()))

    def _set_busy(self, busy: bool, status_text: str) -> None:
        self.busy = busy
        self.status_var.set(status_text)

    def _append_log(self, text: str) -> None:
        line = text.rstrip()
        self._log_buffer.append(line)
        if len(self._log_buffer) > 1000:
            self._log_buffer = self._log_buffer[-1000:]
        if hasattr(self, "log_text"):
            self.log_text.insert(END, line + "\n")
            self.log_text.see(END)

    def _set_snapshot(self, payload: object) -> None:
        if isinstance(payload, str):
            text = payload
        else:
            text = json.dumps(payload, indent=2, ensure_ascii=False)
        self._latest_snapshot_text = text
        if hasattr(self, "snapshot_text"):
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
        workspace_root = self.workspace_root
        if self._orchestrator_instance is None or self._orchestrator_root != workspace_root:
            self._orchestrator_instance = Orchestrator(workspace_root)
            self._orchestrator_root = workspace_root
        return self._orchestrator_instance

    def _runtime(self) -> RuntimeOptions:
        try:
            max_blocks = max(1, int(self.max_steps_var.get().strip() or "5"))
        except ValueError as exc:
            raise ValueError("Max planned steps must be an integer.") from exc
        preset_id, model, effort = self._selected_runtime_model()
        return RuntimeOptions(
            model=model,
            model_preset=preset_id,
            model_selection_mode="slug",
            model_slug_input=model,
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
        if not self.selected_project_id:
            return None
        return self.project_rows.get(self.selected_project_id)

    def _project_dir(self) -> Path:
        project_dir = self.project_dir_var.get().strip()
        if not project_dir:
            raise ValueError("Project directory is required.")
        return Path(project_dir)

    def _prompt_value(self) -> str:
        return self.prompt_text.get("1.0", END).strip()

    def _choose_project_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=str(Path.cwd()))
        if chosen:
            self.project_dir_var.set(chosen)
            if not self.project_name_var.get().strip():
                self.project_name_var.set(Path(chosen).name)

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
            "project_count": len(projects),
            "ready_like": ready,
            "running": running,
            "failed": failed,
        }

    def _render_project_list(self, projects: list[ProjectContext]) -> None:
        ordered = sorted(projects, key=lambda item: item.metadata.created_at, reverse=True)
        self.project_rows = {project.metadata.repo_id: project for project in ordered}
        if self.selected_project_id not in self.project_rows:
            if self.current_project is not None and self.current_project.metadata.repo_id in self.project_rows:
                self.selected_project_id = self.current_project.metadata.repo_id
            else:
                self.selected_project_id = None
        for child in self.project_browser_frame.winfo_children():
            child.destroy()
        if not ordered:
            ttk.Label(
                self.project_browser_frame,
                text="No managed projects yet. Use Create New to register the first directory.",
                style="CardMuted.TLabel",
                anchor="w",
            ).pack(fill=X, pady=(0, 10))
        for project in ordered:
            self._build_project_card(
                self.project_browser_frame,
                project,
                selected=project.metadata.repo_id == self.selected_project_id,
            )
        if self.selected_project_id and self.selected_project_id in self.project_rows:
            project = self.project_rows[self.selected_project_id]
            self.project_summary_text.delete("1.0", END)
            self.project_summary_text.insert("1.0", self._project_summary(project))
        elif not ordered:
            self.project_summary_text.delete("1.0", END)
            self.project_summary_text.insert("1.0", "Create a new managed project to get started.")

    def _upsert_project_row(self, project: ProjectContext) -> None:
        repo_id = project.metadata.repo_id
        self.project_rows[repo_id] = project
        if self.selected_project_id is None:
            self.selected_project_id = repo_id
        if self.current_project is not None and self.current_project.metadata.repo_id == repo_id:
            self.current_project = project
        self._render_project_list(list(self.project_rows.values()))

    def _project_summary(self, project: ProjectContext, plan_state: ExecutionPlanState | None = None) -> str:
        plan = plan_state or self._orchestrator().load_execution_plan_state(project)
        remaining = [step.step_id for step in plan.steps if step.status != "completed"]
        recent_blocks = read_jsonl_tail(project.paths.block_log_file, 5)
        recent_statuses = [str(item.get("status", "")) for item in recent_blocks][-3:]
        lines = [
            f"Name: {project.metadata.display_name or project.metadata.slug}",
            f"Directory: {project.metadata.repo_path}",
            f"GitHub: {project.metadata.origin_url or 'Not connected'}",
            f"Branch: {project.metadata.branch}",
            f"Status: {project.metadata.current_status}",
            f"Model: {project.runtime.model}  ({project.runtime.effort})",
            f"Verification: {plan.default_test_command or project.runtime.test_cmd}",
            f"Remaining Steps: {', '.join(remaining) if remaining else 'None'}",
            f"Closeout: {plan.closeout_status}",
        ]
        if plan.plan_title.strip():
            lines.append(f"Plan Title: {plan.plan_title.strip()}")
        if project.metadata.last_run_at:
            lines.append(f"Last Run: {project.metadata.last_run_at}")
        if recent_statuses:
            lines.append(f"Recent Blocks: {', '.join(recent_statuses)}")
        return "\n".join(lines)

    def load_selected_project_into_form(self) -> None:
        project = self._selected_project()
        if project is None:
            messagebox.showinfo("codex-auto", "Select a managed project first.")
            return
        self._select_project_card(project.metadata.repo_id)
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
                messagebox.showinfo("codex-auto", "Save the project first or select a managed project.")
                return
        orchestrator = self._orchestrator()
        plan_state = orchestrator.load_execution_plan_state(project)
        self._load_project_into_ui(project, plan_state, switch_to_flow=True)

    def _display_name_from_form(self) -> str:
        provided = self.project_name_var.get().strip()
        if provided:
            return provided
        return self._project_dir().name

    def _origin_url_from_form(self) -> str:
        mode = self.github_connection_var.get().strip()
        if mode == GITHUB_CONNECTION_NONE:
            return ""
        if mode == GITHUB_CONNECTION_MANUAL:
            origin_url = self.origin_url_var.get().strip()
            if not origin_url:
                raise ValueError("GitHub URL is required when the manual connection mode is selected.")
            return origin_url
        return ""

    def save_project_setup(self) -> None:
        self._persist_project_setup(switch_to_flow=False)

    def advance_from_setup(self) -> None:
        self._persist_project_setup(switch_to_flow=True)

    def _persist_project_setup(self, switch_to_flow: bool) -> None:
        try:
            project_dir = self._project_dir()
            runtime = self._runtime()
            branch = self.branch_var.get().strip() or "main"
            origin_url = self._origin_url_from_form()
            display_name = self._display_name_from_form()
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
                display_name=display_name,
            )
            plan_state = orchestrator.load_execution_plan_state(project)
            self.queue.put(("loaded_project", (project, plan_state, switch_to_flow)))
            self.queue.put(("project_row", project))
            self.queue.put(("snapshot", self._project_summary(project, plan_state)))

        action_label = "Save project setup and open flow" if switch_to_flow else "Save project setup"
        self._run_async(action_label, worker)

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
        self.selected_project_id = project.metadata.repo_id
        self.current_plan = plan_state
        self._populate_project_form(project)
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
        self._render_project_list(list(self.project_rows.values()))
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
