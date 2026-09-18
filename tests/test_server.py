import os
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from starlette.testclient import TestClient
from backend.server import app


class TestServerEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")

    def test_frontend_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Local AI Waifu", response.text)
        self.assertIn("renderCanvas", response.text)

    def test_models_list_endpoint(self):
        response = self.client.get("/api/models")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("models", data)
        self.assertIn("scan_directories", data)

    def test_characters_endpoint(self):
        response = self.client.get("/api/characters")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("characters", data)
        self.assertIn("active_character", data)
        
        # Test character selection
        res_sel = self.client.post("/api/characters/select", json={"character_file": "procedural"})
        self.assertEqual(res_sel.status_code, 200)
        self.assertEqual(res_sel.json()["active_character"], "procedural")


    def test_config_endpoints(self):
        # GET config
        res_get = self.client.get("/api/config")
        self.assertEqual(res_get.status_code, 200)
        cfg = res_get.json()
        self.assertIn("llm", cfg)

        # POST config update
        update_payload = {"settings": {"test_key": "test_value"}}
        res_post = self.client.post("/api/config", json=update_payload)
        self.assertEqual(res_post.status_code, 200)
        self.assertEqual(res_post.json()["config"]["test_key"], "test_value")

    def test_voice_selection_validation(self):
        # Invalid file
        res_invalid = self.client.post("/api/voice/select", json={"voice_path": "non_existent.wav"})
        self.assertEqual(res_invalid.status_code, 400)

        # Valid wav file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFF" + b"\x00" * 40)
            valid_path = f.name

        try:
            res_valid = self.client.post("/api/voice/select", json={"voice_path": valid_path})
            self.assertEqual(res_valid.status_code, 200)
            data = res_valid.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["voice"]["format"], "wav")
        finally:
            if os.path.exists(valid_path):
                os.remove(valid_path)

    def test_websocket_chat_streaming(self):
        with self.client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"text": "Hello there waifu!"})
            
            received_tokens = []
            received_audio_packets = []
            done_received = False

            while not done_received:
                msg = ws.receive_json()
                if msg["type"] == "token":
                    received_tokens.append(msg["content"])
                elif msg["type"] == "audio_packet":
                    received_audio_packets.append(msg)
                    self.assertIn("emotion", msg)
                    self.assertIn("blendshapes", msg)
                    self.assertIn("visemes", msg)
                    self.assertIn("audio_base64", msg)
                elif msg["type"] == "done":
                    done_received = True

            self.assertTrue(done_received)
            self.assertGreater(len(received_tokens), 0)
            self.assertGreater(len(received_audio_packets), 0)

    def test_character_upload(self):
        # Test invalid extension
        res_invalid = self.client.post(
            "/api/characters/upload",
            files={"file": ("test.txt", b"invalid content", "text/plain")}
        )
        self.assertEqual(res_invalid.status_code, 400)

        # Test valid glb upload
        res_valid = self.client.post(
            "/api/characters/upload",
            files={"file": ("test_custom_waifu.glb", b"glTF" + b"\x00" * 20, "model/gltf-binary")}
        )
        self.assertEqual(res_valid.status_code, 200)
        data = res_valid.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["filename"], "test_custom_waifu.glb")

        # Clean up test file
        test_file = Path(__file__).parent.parent / "frontend" / "characters" / "test_custom_waifu.glb"
        if test_file.exists():
            test_file.unlink()


if __name__ == "__main__":
    unittest.main()

