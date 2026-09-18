import os
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import ConfigManager


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_file = os.path.join(self.temp_dir.name, "test_config.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_config_creation(self):
        cfg = ConfigManager(self.config_file)
        self.assertTrue(os.path.exists(self.config_file))
        self.assertEqual(cfg.get("llm", "n_ctx"), 4096)
        self.assertEqual(cfg.get("tts", "engine"), "cosyvoice")

    def test_set_and_save(self):
        cfg = ConfigManager(self.config_file)
        cfg.set("llm", "active_model_path", "C:/models/test.gguf")
        cfg.set("tts", "active_voice_path", "C:/voices/my_waifu.wav")
        
        # Reload fresh instance
        cfg2 = ConfigManager(self.config_file)
        self.assertEqual(cfg2.get("llm", "active_model_path"), "C:/models/test.gguf")
        self.assertEqual(cfg2.get("tts", "active_voice_path"), "C:/voices/my_waifu.wav")


if __name__ == "__main__":
    unittest.main()
