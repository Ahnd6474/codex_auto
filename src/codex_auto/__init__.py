from __future__ import annotations

import importlib
import sys

from jakal_flow import __version__

__all__ = ["__version__"]


def _alias_module(module_name: str) -> None:
    module = importlib.import_module(f"jakal_flow.{module_name}")
    globals()[module_name] = module
    sys.modules[f"{__name__}.{module_name}"] = module


for _module_name in ("planning", "orchestrator", "ui_bridge"):
    _alias_module(_module_name)
