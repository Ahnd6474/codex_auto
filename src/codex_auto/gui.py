from __future__ import annotations

import json
import queue
import threading
import traceback
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, W, filedialog, messagebox, StringVar, Tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable

from .models import ProjectContext, RuntimeOptions
from .orchestrator import Orchestrator


class CodexAutoGUI:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Codex Auto")
        self.root.geometry("1400x860")
        self.root.minsize(1100, 700)

        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.repo_index: dict[str, dict[str, object]] = {}

        self.repo_url_var = StringVar()
        self.branch_var = StringVar(value="main")
        self.workspace_root_var = StringVar(value=".codex-auto-workspace")
        self.model_var = StringVar(value="gpt-5")
        self.approval_var = StringVar(value="never")
        self.sandbox_var = StringVar(value="workspace-write")
        self.test_cmd_var = StringVar(value="python -m pytest")
        self.max_blocks_var = StringVar(value="1")
        self.long_term_plan_var = StringVar()
        self.allow_push_var = StringVar(value="false")

        self._build_layout()
        self._schedule_queue_poll()
        self.refresh_repositories()

    def _build_layout(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        root_frame = ttk.Frame(self.root, padding=12)
        root_frame.pack(fill=BOTH, expand=True)

        left = ttk.Frame(root_frame)
        left.pack(side=LEFT, fill=BOTH, expand=False, padx=(0, 12))

        right = ttk.Frame(root_frame)
        right.pack(side=RIGHT, fill=BOTH, expand=True)

        self._build_repo_list(left)
        self._build_form(right)
        self._build_output(right)

    def _build_repo_list(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Managed Repositories", padding=10)
        frame.pack(fill=BOTH, expand=True)

        columns = ("slug", "branch", "status", "last_run")
        self.repo_tree = ttk.Treeview(frame, columns=columns, show="headings", height=18)
        self.repo_tree.heading("slug", text="Slug")
        self.repo_tree.heading("branch", text="Branch")
        self.repo_tree.heading("status", text="Status")
        self.repo_tree.heading("last_run", text="Last Run")
        self.repo_tree.column("slug", width=260, anchor=W)
        self.repo_tree.column("branch", width=80, anchor=W)
        self.repo_tree.column("status", width=160, anchor=W)
        self.repo_tree.column("last_run", width=170, anchor=W)
        self.repo_tree.pack(fill=BOTH, expand=True)
        self.repo_tree.bind("<<TreeviewSelect>>", self._on_repo_selected)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Refresh", command=self.refresh_repositories).pack(side=LEFT)
        ttk.Button(buttons, text="Load Selected", command=self.load_selected_repository).pack(side=LEFT, padx=(8, 0))

    def _build_form(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Run Configuration", padding=10)
        frame.pack(fill="x")

        def add_row(row: int, label: str, variable: StringVar, width: int = 70) -> ttk.Entry:
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky=W, padx=(0, 8), pady=4)
            entry = ttk.Entry(frame, textvariable=variable, width=width)
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            return entry

        frame.columnconfigure(1, weight=1)
        add_row(0, "Repo URL", self.repo_url_var)
        add_row(1, "Branch", self.branch_var, width=28)

        workspace_entry = add_row(2, "Workspace Root", self.workspace_root_var)
        ttk.Button(frame, text="Browse", command=self._choose_workspace_root).grid(row=2, column=2, padx=(8, 0), pady=4)

        add_row(3, "Model", self.model_var, width=28)
        add_row(4, "Approval Mode", self.approval_var, width=28)
        add_row(5, "Sandbox Mode", self.sandbox_var, width=28)
        add_row(6, "Test Command", self.test_cmd_var)
        add_row(7, "Max Blocks", self.max_blocks_var, width=12)

        add_row(8, "Long-Term Plan", self.long_term_plan_var)
        ttk.Button(frame, text="Browse", command=self._choose_long_term_plan).grid(row=8, column=2, padx=(8, 0), pady=4)

        ttk.Label(frame, text="Allow Push").grid(row=9, column=0, sticky=W, padx=(0, 8), pady=4)
        allow_push_box = ttk.Combobox(
            frame,
            textvariable=self.allow_push_var,
            state="readonly",
            values=["false", "true"],
            width=10,
        )
        allow_push_box.grid(row=9, column=1, sticky=W, pady=4)

        actions = ttk.Frame(frame)
        actions.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        self.action_buttons: list[ttk.Button] = []
        for label, handler in [
            ("Init Repo", self.init_repo),
            ("Run", self.run_blocks),
            ("Resume", self.resume_run),
            ("Status", self.show_status),
            ("History", self.show_history),
            ("Report", self.show_report),
        ]:
            button = ttk.Button(actions, text=label, command=handler)
            button.pack(side=LEFT, padx=(0, 8))
            self.action_buttons.append(button)

        ttk.Label(frame, text="Use GitHub URL or an accessible git remote/local path.").grid(
            row=11, column=0, columnspan=3, sticky=W, pady=(10, 0)
        )

        workspace_entry.focus_set()

    def _build_output(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Activity", padding=10)
        frame.pack(fill=BOTH, expand=True, pady=(12, 0))

        self.status_var = StringVar(value="Idle")
        ttk.Label(frame, textvariable=self.status_var).pack(anchor=W)

        self.tabs = ttk.Notebook(frame)
        self.tabs.pack(fill=BOTH, expand=True, pady=(8, 0))

        log_tab = ttk.Frame(self.tabs)
        self.log_text = ScrolledText(log_tab, wrap="word", height=14)
        self.log_text.pack(fill=BOTH, expand=True)
        self.log_text.configure(state="disabled")
        self.tabs.add(log_tab, text="Log")

        detail_tab = ttk.Frame(self.tabs)
        self.detail_text = ScrolledText(detail_tab, wrap="word", height=22)
        self.detail_text.pack(fill=BOTH, expand=True)
        self.detail_text.configure(state="disabled")
        self.tabs.add(detail_tab, text="Details")

    def _choose_workspace_root(self) -> None:
        chosen = filedialog.askdirectory(initialdir=str(Path.cwd()))
        if chosen:
            self.workspace_root_var.set(chosen)
            self.refresh_repositories()

    def _choose_long_term_plan(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Select LONG_TERM_PLAN.md",
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
        )
        if chosen:
            self.long_term_plan_var.set(chosen)

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

    def _set_busy(self, busy: bool, label: str = "Idle") -> None:
        self.busy = busy
        self.status_var.set(label)
        for button in self.action_buttons:
            button.state(["disabled"] if busy else ["!disabled"])

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
                self._set_busy(False, data.get("status", "Idle"))
                if "details" in data:
                    self._set_details(str(data["details"]))
                self.refresh_repositories()
            elif event == "error":
                self._set_busy(False, "Failed")
                self._append_log(str(payload))
                messagebox.showerror("Codex Auto", str(payload))
        self._schedule_queue_poll()

    def _orchestrator(self) -> Orchestrator:
        workspace_root = Path(self.workspace_root_var.get().strip() or ".codex-auto-workspace")
        return Orchestrator(workspace_root)

    def _runtime(self) -> RuntimeOptions:
        max_blocks_text = self.max_blocks_var.get().strip() or "1"
        try:
            max_blocks = max(1, int(max_blocks_text))
        except ValueError as exc:
            raise ValueError("Max Blocks must be an integer.") from exc
        return RuntimeOptions(
            model=self.model_var.get().strip() or "gpt-5",
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
            raise ValueError("Repo URL is required.")
        return repo_url, branch

    def _long_term_path(self) -> Path | None:
        value = self.long_term_plan_var.get().strip()
        return Path(value) if value else None

    def _run_async(self, label: str, worker: Callable[[], object]) -> None:
        if self.busy:
            messagebox.showinfo("Codex Auto", "Another operation is already running.")
            return
        self._set_busy(True, label)
        self._append_log(f"[start] {label}")

        def target() -> None:
            try:
                result = worker()
                details = self._render_result(result)
                self.queue.put(("done", {"status": f"{label} completed", "details": details}))
                self.queue.put(("log", f"[done] {label}"))
            except Exception as exc:
                stack = traceback.format_exc()
                self.queue.put(("error", f"{label} failed: {exc}\n\n{stack}"))

        threading.Thread(target=target, daemon=True).start()

    def _render_result(self, result: object) -> str:
        if isinstance(result, ProjectContext):
            return json.dumps(
                {
                    "metadata": result.metadata.to_dict(),
                    "loop_state": result.loop_state.to_dict(),
                },
                indent=2,
            )
        if isinstance(result, list):
            return json.dumps(result, indent=2)
        if isinstance(result, dict):
            return json.dumps(result, indent=2)
        return str(result)

    def refresh_repositories(self) -> None:
        try:
            projects = self._orchestrator().list_projects()
        except Exception as exc:
            self._append_log(f"[warn] list-repos failed: {exc}")
            return

        self.repo_index = {}
        for item in self.repo_tree.get_children():
            self.repo_tree.delete(item)

        rows: list[dict[str, object]] = []
        for project in projects:
            row = {
                "repo_id": project.metadata.repo_id,
                "slug": project.metadata.slug,
                "repo_url": project.metadata.repo_url,
                "branch": project.metadata.branch,
                "status": project.metadata.current_status,
                "last_run_at": project.metadata.last_run_at,
                "safe_revision": project.metadata.current_safe_revision,
            }
            self.repo_index[project.metadata.repo_id] = row
            self.repo_tree.insert(
                "",
                END,
                iid=project.metadata.repo_id,
                values=(
                    project.metadata.slug,
                    project.metadata.branch,
                    project.metadata.current_status,
                    project.metadata.last_run_at or "",
                ),
            )
            rows.append(row)
        self._set_details(json.dumps(rows, indent=2))

    def _on_repo_selected(self, _event: object) -> None:
        self.load_selected_repository(show_message=False)

    def load_selected_repository(self, show_message: bool = True) -> None:
        selected = self.repo_tree.selection()
        if not selected:
            if show_message:
                messagebox.showinfo("Codex Auto", "Select a managed repository first.")
            return
        repo_id = selected[0]
        row = self.repo_index.get(repo_id)
        if not row:
            return
        self.repo_url_var.set(str(row["repo_url"]))
        self.branch_var.set(str(row["branch"]))
        if show_message:
            self._append_log(f"[info] loaded {row['slug']}")

    def init_repo(self) -> None:
        try:
            repo_url, branch = self._repo_inputs()
            runtime = self._runtime()
            long_term_path = self._long_term_path()
        except Exception as exc:
            messagebox.showerror("Codex Auto", str(exc))
            return
        self._run_async(
            "Init Repo",
            lambda: self._orchestrator().init_repo(
                repo_url=repo_url,
                branch=branch,
                runtime=runtime,
                long_term_plan_path=long_term_path,
            ),
        )

    def run_blocks(self) -> None:
        try:
            repo_url, branch = self._repo_inputs()
            runtime = self._runtime()
            long_term_path = self._long_term_path()
        except Exception as exc:
            messagebox.showerror("Codex Auto", str(exc))
            return
        self._run_async(
            "Run",
            lambda: self._orchestrator().run(
                repo_url=repo_url,
                branch=branch,
                runtime=runtime,
                long_term_plan_path=long_term_path,
                resume=False,
            ),
        )

    def resume_run(self) -> None:
        try:
            repo_url, branch = self._repo_inputs()
            runtime = self._runtime()
        except Exception as exc:
            messagebox.showerror("Codex Auto", str(exc))
            return
        self._run_async(
            "Resume",
            lambda: self._orchestrator().resume(
                repo_url=repo_url,
                branch=branch,
                runtime=runtime,
            ),
        )

    def show_status(self) -> None:
        try:
            repo_url, branch = self._repo_inputs()
        except Exception as exc:
            messagebox.showerror("Codex Auto", str(exc))
            return
        self._run_async(
            "Status",
            lambda: self._orchestrator().status(repo_url=repo_url, branch=branch),
        )

    def show_history(self) -> None:
        try:
            repo_url, branch = self._repo_inputs()
        except Exception as exc:
            messagebox.showerror("Codex Auto", str(exc))
            return
        self._run_async(
            "History",
            lambda: self._orchestrator().history(repo_url=repo_url, branch=branch, limit=20),
        )

    def show_report(self) -> None:
        try:
            repo_url, branch = self._repo_inputs()
        except Exception as exc:
            messagebox.showerror("Codex Auto", str(exc))
            return

        def worker() -> dict[str, object]:
            orchestrator = self._orchestrator()
            path = orchestrator.report(repo_url=repo_url, branch=branch)
            content = path.read_text(encoding="utf-8")
            return {"report_path": str(path), "report": json.loads(content)}

        self._run_async("Report", worker)


def main() -> int:
    root = Tk()
    app = CodexAutoGUI(root)
    app._append_log("GUI ready")
    root.mainloop()
    return 0
