import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.tts import (
    MockTTSClient,
    generate_mock_speech_wav,
    extract_audio_visemes,
)


class TestTTSPipeline(unittest.TestCase):
    def test_mock_tts_generation(self):
        client = MockTTSClient()
        wav = client.synthesize("Hello world! How are you?", emotion="happy")
        self.assertIsInstance(wav, bytes)
        self.assertTrue(wav.startswith(b"RIFF"))
        self.assertGreater(len(wav), 1000)

    def test_viseme_extraction(self):
        wav = generate_mock_speech_wav("Testing audio viseme generation for 3D avatar lip sync.")
        frames = extract_audio_visemes(wav)
        self.assertGreater(len(frames), 5)
        
        # Check structure of each viseme frame
        first_frame = frames[0]
        self.assertIn("timestamp", first_frame)
        self.assertIn("openness", first_frame)
        self.assertIn("visemes", first_frame)
        self.assertIn("aa", first_frame["visemes"])
        self.assertIn("ih", first_frame["visemes"])
        self.assertIn("ou", first_frame["visemes"])

    def test_edge_tts_client_instance(self):
        from backend.tts import EdgeTTSClient, CosyVoiceTTSClient
        client = EdgeTTSClient(voice_name="en-US-AnaNeural")
        self.assertEqual(client.voice_name, "en-US-AnaNeural")
        
        cosy = CosyVoiceTTSClient()
        self.assertTrue(hasattr(cosy, "fallback_tts"))
        self.assertIsInstance(cosy.fallback_tts, EdgeTTSClient)


if __name__ == "__main__":
    unittest.main()
