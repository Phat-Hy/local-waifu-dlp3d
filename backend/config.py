"""
Configuration Manager for Local AI Waifu
Handles user settings, persistent config.json, model scan paths, and active model/voice selections.
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

DEFAULT_CONFIG_PATH = "config.json"

DEFAULT_SYSTEM_PROMPT = """You are an affectionate, expressive anime AI companion.
You speak naturally and empathetically.
Always prefix your responses with an emotion tag in brackets at the very beginning of sentences where your emotion changes.
Supported emotion tags: [happy], [smile], [blush], [tsundere], [shy], [surprised], [sad], [thinking], [neutral].
Example:
[happy] Master, welcome back! [blush] I was hoping you would talk to me today.
"""

DEFAULT_CONFIG: Dict[str, Any] = {
    "server": {
        "host": "127.0.0.1",
        "port": 18002,
    },
    "llm": {
        "active_model_path": "",
        "scan_directories": [
            "G:\\Program\\Odysseus\\model\\hub",
            "models",
        ],
        "n_ctx": 4096,
        "n_gpu_layers": -1,  # -1 for all layers to GPU
        "temperature": 0.7,
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
    },
    "tts": {
        "engine": "cosyvoice",  # cosyvoice | edge_tts
        "voice_name": "en-US-AnaNeural",
        "active_voice_path": "",  # Path to user-selected reference .wav file
        "sample_rate": 22050,
        "speed": 1.0,
    },
    "avatar": {
        "model_file": "default.vrm",
        "enable_cloth_simulation": True,
        "debug_mode": False,
    }
}


class ConfigManager:
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Merge defaults
                self.config = self._deep_merge(DEFAULT_CONFIG, data)
            except Exception as e:
                print(f"[ConfigManager] Error loading config: {e}. Using defaults.")
                self.config = json.loads(json.dumps(DEFAULT_CONFIG))
        else:
            self.config = json.loads(json.dumps(DEFAULT_CONFIG))
            self.save()
        return self.config

    def save(self) -> None:
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"[ConfigManager] Error saving config: {e}")

    def _deep_merge(self, base: dict, override: dict) -> dict:
        merged = base.copy()
        for k, v in override.items():
            if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
                merged[k] = self._deep_merge(merged[k], v)
            else:
                merged[k] = v
        return merged

    def get(self, *keys, default=None):
        curr = self.config
        for k in keys:
            if isinstance(curr, dict) and k in curr:
                curr = curr[k]
            else:
                return default
        return curr

    def set(self, *keys_and_value):
        if len(keys_and_value) < 2:
            return
        keys = keys_and_value[:-1]
        val = keys_and_value[-1]
        curr = self.config
        for k in keys[:-1]:
            if k not in curr or not isinstance(curr[k], dict):
                curr[k] = {}
            curr = curr[k]
        curr[keys[-1]] = val
        self.save()
