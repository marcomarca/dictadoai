import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from dictado_ai.config import Settings
from dictado_ai.history import HistoryEntry, HistoryManager
from dictado_ai.modes import ModesManager
from dictado_ai.vocabulary import VocabularyManager
from dictado_ai.gui.web_window import WebBridge


class TestWebBridgeExtended(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        self.history_file = base_dir / "test_history.jsonl"
        self.vocab_file = base_dir / "test_vocab.json"
        self.modes_file = base_dir / "test_modes.json"

        self.history_mgr = HistoryManager(self.history_file)
        self.vocab_mgr = VocabularyManager(self.vocab_file)
        self.modes_mgr = ModesManager(self.modes_file)
        self.settings = Settings.default()

        self.mock_window = MagicMock()
        self.bridge = WebBridge(
            self.settings,
            self.history_mgr,
            self.mock_window,
            vocabulary_manager=self.vocab_mgr,
            modes_manager=self.modes_mgr,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_vocabulary_slots(self):
        # 1. Agregar término
        res = self.bridge.addVocabulary("Kubernetes", "K8s")
        item = json.loads(res)
        self.assertEqual(item["word"], "Kubernetes")
        self.assertEqual(item["replacement"], "K8s")
        item_id = item["id"]

        # 2. Listar términos
        vocab_json = self.bridge.getVocabulary()
        items = json.loads(vocab_json)
        self.assertEqual(len(items), 1)

        # 3. Borrar término
        ok = self.bridge.deleteVocabulary(item_id)
        self.assertTrue(ok)
        self.assertEqual(len(json.loads(self.bridge.getVocabulary())), 0)

    def test_modes_slots(self):
        # 1. Obtener modos por defecto
        modes_json = self.bridge.getModes()
        modes = json.loads(modes_json)
        self.assertEqual(len(modes), 4)

        # 2. Cambiar modo activo a code
        ok = self.bridge.setActiveMode("code")
        self.assertTrue(ok)
        self.assertEqual(self.modes_mgr.get_active_mode().id, "code")

        # 3. Crear modo personalizado
        created_json = self.bridge.createMode(
            name="Médico",
            description="Términos clínicos y farmacológicos",
            system_prompt="Corrige terminología médica",
            is_raw=False,
        )
        created = json.loads(created_json)
        self.assertEqual(created["name"], "Médico")
        self.assertEqual(len(json.loads(self.bridge.getModes())), 5)

        # 4. Eliminar modo personalizado
        del_ok = self.bridge.deleteMode(created["id"])
        self.assertTrue(del_ok)
        self.assertEqual(len(json.loads(self.bridge.getModes())), 4)

    def test_dashboard_metrics_slot(self):
        from datetime import datetime, timezone

        # Con historial vacío
        metrics_json = self.bridge.getDashboardMetrics()
        metrics = json.loads(metrics_json)
        self.assertEqual(metrics["avg_wpm"], 0)
        self.assertEqual(metrics["total_words"], 0)

        # Agregando entrada reciente
        entry = HistoryEntry(
            id="e1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            text="Prueba de métricas",
            word_count=50,
            duration_sec=12.0,
            wpm=150.0,
        )
        self.history_mgr.append_entry(entry)

        metrics_json = self.bridge.getDashboardMetrics()
        metrics = json.loads(metrics_json)
        self.assertEqual(metrics["total_words"], 50)
        self.assertEqual(metrics["total_dictations"], 1)


if __name__ == "__main__":
    unittest.main()
