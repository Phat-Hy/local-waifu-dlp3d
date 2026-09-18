import os
import struct
import tempfile
import unittest
from pathlib import Path
import sys

# Ensure backend can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.scanner import (
    parse_gguf_metadata,
    scan_directory_for_models,
    validate_audio_file,
    GGUF_MAGIC,
    GGUF_TYPE_STRING,
    GGUF_TYPE_UINT32,
)


class TestModelScanner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_audio_validation(self):
        # Non-existent file
        res = validate_audio_file("non_existent_audio.wav")
        self.assertFalse(res["valid"])
        self.assertIn("does not exist", res["error"])

        # Real wav file
        wav_path = os.path.join(self.dir_path, "sample_voice.wav")
        with open(wav_path, "wb") as f:
            f.write(b"RIFF" + b"\x00" * 40)
        
        res = validate_audio_file(wav_path)
        self.assertTrue(res["valid"])
        self.assertEqual(res["format"], "wav")

        # Unsupported format
        txt_path = os.path.join(self.dir_path, "sample.txt")
        with open(txt_path, "w") as f:
            f.write("hello")
        res = validate_audio_file(txt_path)
        self.assertFalse(res["valid"])
        self.assertIn("Unsupported audio format", res["error"])

    def test_synthetic_gguf_parsing(self):
        # Create a valid synthetic GGUF v3 file
        gguf_path = os.path.join(self.dir_path, "test_qwen.gguf")
        
        with open(gguf_path, "wb") as f:
            # Header
            f.write(GGUF_MAGIC)  # Magic: GGUF
            f.write(struct.pack("<I", 3))  # Version: 3
            f.write(struct.pack("<Q", 128))  # Tensor count: 128
            f.write(struct.pack("<Q", 2))  # KV count: 2 pairs

            # KV Pair 1: general.architecture = "qwen2"
            key1 = b"general.architecture"
            f.write(struct.pack("<Q", len(key1)))
            f.write(key1)
            f.write(struct.pack("<I", GGUF_TYPE_STRING))
            val1 = b"qwen2"
            f.write(struct.pack("<Q", len(val1)))
            f.write(val1)

            # KV Pair 2: qwen2.context_length = 32768
            key2 = b"qwen2.context_length"
            f.write(struct.pack("<Q", len(key2)))
            f.write(key2)
            f.write(struct.pack("<I", GGUF_TYPE_UINT32))
            f.write(struct.pack("<I", 32768))

        # Parse metadata
        meta = parse_gguf_metadata(gguf_path)
        self.assertTrue(meta["valid"])
        self.assertEqual(meta["gguf_version"], 3)
        self.assertEqual(meta["tensor_count"], 128)
        self.assertEqual(meta["architecture"], "qwen2")
        self.assertEqual(meta["context_length"], 32768)

        # Test directory scanning
        models = scan_directory_for_models([self.dir_path])
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["filename"], "test_qwen.gguf")
        self.assertEqual(models[0]["architecture"], "qwen2")


if __name__ == "__main__":
    unittest.main()
