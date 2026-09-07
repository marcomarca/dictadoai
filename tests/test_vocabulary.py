import tempfile
import unittest
from pathlib import Path

from dictado_ai.vocabulary import VocabularyManager, VocabularyEntry


class TestVocabularyManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vocab_file = Path(self.temp_dir.name) / "test_vocabulary.json"
        self.manager = VocabularyManager(self.vocab_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_and_get_all(self):
        item1 = self.manager.add_item("PySide", "PySide6")
        self.assertIsNotNone(item1)
        self.assertEqual(item1.word, "PySide")
        self.assertEqual(item1.replacement, "PySide6")

        item2 = self.manager.add_item("Superwhisper", "Super Whisper")
        self.assertIsNotNone(item2)

        items = self.manager.get_all()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].word, "PySide")
        self.assertEqual(items[1].word, "Superwhisper")

    def test_add_duplicate_updates_replacement(self):
        self.manager.add_item("API", "Application Programming Interface")
        self.assertEqual(len(self.manager.get_all()), 1)

        # Re-añadir con reemplazo diferente
        self.manager.add_item("API", "API REST")
        items = self.manager.get_all()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].replacement, "API REST")

    def test_delete_item(self):
        item = self.manager.add_item("Borrarme", "")
        self.assertEqual(len(self.manager.get_all()), 1)

        ok = self.manager.delete_item(item.id)
        self.assertTrue(ok)
        self.assertEqual(len(self.manager.get_all()), 0)

        not_found = self.manager.delete_item("non-existent")
        self.assertFalse(not_found)

    def test_toggle_item(self):
        item = self.manager.add_item("Activo", "")
        self.assertTrue(item.enabled)

        self.manager.toggle_item(item.id)
        items = self.manager.get_all()
        self.assertFalse(items[0].enabled)

        self.manager.toggle_item(item.id)
        items = self.manager.get_all()
        self.assertTrue(items[0].enabled)

    def test_apply_replacements(self):
        self.manager.add_item("mi correo", "contacto@dictado.ai")
        self.manager.add_item("ia", "Inteligencia Artificial")

        text = "Por favor envía esto a mi correo para analizarlo con IA y no con otra cosa."
        result = self.manager.apply_replacements(text)

        self.assertIn("contacto@dictado.ai", result)
        self.assertIn("Inteligencia Artificial", result)
        self.assertNotIn("mi correo", result)

    def test_get_prompt_hints(self):
        self.manager.add_item("DictadoAI", "")
        self.manager.add_item("Whisper", "OpenAI Whisper")

        hints = self.manager.get_prompt_hints()
        self.assertEqual(len(hints), 2)
        self.assertIn("DictadoAI", hints)
        self.assertIn("Whisper (reemplazar por 'OpenAI Whisper')", hints)


if __name__ == "__main__":
    unittest.main()
