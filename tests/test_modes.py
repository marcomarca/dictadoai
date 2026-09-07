import tempfile
import unittest
from pathlib import Path

from dictado_ai.modes import ModesManager, DictationModeConfig


class TestModesManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.modes_file = Path(self.temp_dir.name) / "test_modes.json"
        self.manager = ModesManager(self.modes_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_modes_seeded(self):
        modes = self.manager.get_all()
        self.assertEqual(len(modes), 4)

        active = self.manager.get_active_mode()
        self.assertEqual(active.id, "default")
        self.assertTrue(active.active)

        mode_ids = [m.id for m in modes]
        self.assertIn("default", mode_ids)
        self.assertIn("code", mode_ids)
        self.assertIn("email", mode_ids)
        self.assertIn("raw", mode_ids)

    def test_set_active_mode(self):
        ok = self.manager.set_active_mode("code")
        self.assertTrue(ok)

        active = self.manager.get_active_mode()
        self.assertEqual(active.id, "code")
        self.assertTrue(active.active)

        # Verificar que el anterior ya no esté activo
        default_mode = next(m for m in self.manager.get_all() if m.id == "default")
        self.assertFalse(default_mode.active)

    def test_add_and_delete_custom_mode(self):
        new_mode = self.manager.add_mode(
            name="Markdown Notes",
            description="Formato para notas rápidas",
            system_prompt="Formatea con encabezados markdown",
        )
        self.assertIsNotNone(new_mode)
        self.assertEqual(len(self.manager.get_all()), 5)

        # Borrar el modo personalizado
        deleted = self.manager.delete_mode(new_mode.id)
        self.assertTrue(deleted)
        self.assertEqual(len(self.manager.get_all()), 4)

    def test_cannot_delete_default_mode(self):
        deleted = self.manager.delete_mode("default")
        self.assertFalse(deleted)
        self.assertEqual(len(self.manager.get_all()), 4)

    def test_raw_mode_properties(self):
        self.manager.set_active_mode("raw")
        active = self.manager.get_active_mode()
        self.assertTrue(active.is_raw)
        self.assertEqual(active.system_prompt, "")


if __name__ == "__main__":
    unittest.main()
