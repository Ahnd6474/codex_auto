from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import jakal_flow.model_providers as model_providers


class ModelProvidersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="jakal-flow-model-providers-"))
        model_providers._LOCAL_MODEL_CATALOG_CACHE.clear()

    def tearDown(self) -> None:
        model_providers._LOCAL_MODEL_CATALOG_CACHE.clear()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_manifest(self, root: Path, model_name: str) -> None:
        family, tag = model_name.split(":", 1)
        manifest_path = root / "manifests" / "registry.ollama.ai" / "library" / family / tag
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text("{}", encoding="utf-8")

    def test_discover_local_model_catalog_includes_managed_ollama_store_models_when_cli_is_unavailable(self) -> None:
        managed_root = self.temp_dir / "managed-store"
        third_party_root = self.temp_dir / "third-party"
        self._write_manifest(managed_root, "qwen2.5-coder:0.5b")

        with mock.patch.object(model_providers, "_ollama_cli_models", return_value=[]):
            catalog = model_providers.discover_local_model_catalog(
                third_party_root=third_party_root,
                managed_ollama_root=managed_root,
                force_refresh=True,
            )

        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0]["model"], "qwen2.5-coder:0.5b")
        self.assertEqual(catalog[0]["source"], "managed-ollama-store")
        self.assertTrue(catalog[0]["installed"])


if __name__ == "__main__":
    unittest.main()
