"""
Local LLM Service Layer
Provides native llama-cpp-python direct GPU inference and fallback HTTP OpenAI-compatible endpoints.
Integrates with EmotionStreamProcessor for streaming dialogue, emotion tags, and 3D avatar blendshapes.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Generator, Dict, Any, List, Optional
from backend.emotion import EmotionStreamProcessor

# Ensure llama_cpp from Odysseus virtual environment is accessible if not in base environment
ODYSSEUS_SITE_PACKAGES = Path(r"G:\Program\Odysseus\odysseus\venv\Lib\site-packages")
if ODYSSEUS_SITE_PACKAGES.exists() and str(ODYSSEUS_SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(ODYSSEUS_SITE_PACKAGES))


class NativeLlamaEngine:
    """
    Direct in-process GGUF LLM execution using llama-cpp-python with full CUDA acceleration.
    """
    def __init__(
        self,
        model_path: str,
        n_gpu_layers: int = -1,
        n_ctx: int = 2048,
        temperature: float = 0.7,
        max_tokens: int = 150,
    ):
        self.model_path = model_path
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.llm = None
        self.load_error = None
        self.load_model()

    def load_model(self):
        try:
            import llama_cpp
            print(f"[NativeLlamaEngine] Loading GGUF model from {self.model_path} (n_gpu_layers={self.n_gpu_layers}, n_ctx={self.n_ctx})...")
            self.llm = llama_cpp.Llama(
                model_path=str(self.model_path),
                n_gpu_layers=self.n_gpu_layers,
                n_ctx=self.n_ctx,
                verbose=False,
            )
            print(f"[NativeLlamaEngine] Model successfully loaded on GPU!")
            self.load_error = None
        except Exception as e:
            self.load_error = str(e)
            print(f"[NativeLlamaEngine] Failed to load GGUF model: {e}")
            self.llm = None

    def is_loaded(self) -> bool:
        return self.llm is not None

    def stream_chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        if not self.is_loaded():
            yield {"type": "error", "error": f"Model not loaded: {self.load_error}"}
            return

        processor = EmotionStreamProcessor()
        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        try:
            generator = self.llm.create_chat_completion(
                messages=formatted_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True,
            )

            for chunk in generator:
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    sentences = processor.process_token(content)
                    for s in sentences:
                        yield {
                            "type": "sentence",
                            "text": s["text"],
                            "emotion": s["emotion"],
                            "gesture": s.get("gesture", "none"),
                            "blendshapes": s["blendshapes"],
                        }
                    yield {
                        "type": "token",
                        "token": content,
                    }

            # Flush remaining sentence buffer at stream completion
            final_sentences = processor.flush()
            for s in final_sentences:
                yield {
                    "type": "sentence",
                    "text": s["text"],
                    "emotion": s["emotion"],
                    "gesture": s.get("gesture", "none"),
                    "blendshapes": s["blendshapes"],
                }

        except Exception as e:
            yield {"type": "error", "error": str(e)}


class OpenAILLMEngine:
    """
    Fallback HTTP LLM engine for OpenAI-compatible endpoints (Ollama, LM Studio, vLLM).
    """
    def __init__(
        self,
        api_base: str = "http://127.0.0.1:8000/v1",
        model_name: str = "qwen3.5-4b",
        temperature: float = 0.7,
        max_tokens: int = 512,
    ):
        self.api_base = api_base.rstrip("/")
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

    def check_health(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.api_base}/models")
            with urllib.request.urlopen(req, timeout=2) as response:
                return response.status == 200
        except Exception:
            return False

    def stream_chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        processor = EmotionStreamProcessor()
        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        payload = {
            "model": self.model_name,
            "messages": formatted_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=data_bytes,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                for line in response:
                    line_str = line.decode("utf-8").strip()
                    if not line_str.startswith("data: "):
                        continue
                    data_str = line_str[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            sentences = processor.process_token(content)
                            for s in sentences:
                                yield {
                                    "type": "sentence",
                                    "text": s["text"],
                                    "emotion": s["emotion"],
                                    "gesture": s.get("gesture", "none"),
                                    "blendshapes": s["blendshapes"],
                                }
                            yield {
                                "type": "token",
                                "token": content,
                            }
                    except json.JSONDecodeError:
                        continue

            final_sentences = processor.flush()
            for s in final_sentences:
                yield {
                    "type": "sentence",
                    "text": s["text"],
                    "emotion": s["emotion"],
                    "gesture": s.get("gesture", "none"),
                    "blendshapes": s["blendshapes"],
                }

        except urllib.error.URLError as e:
            yield {
                "type": "error",
                "error": f"Failed to connect to local LLM at {self.api_base}: {e.reason}",
            }


# Global engine manager
_global_engine = None
_global_model_path = None


def get_llm_engine(
    model_path: Optional[str] = None,
    n_gpu_layers: int = -1,
    n_ctx: int = 2048,
    temperature: float = 0.7,
) -> Optional[NativeLlamaEngine]:
    """
    Returns active NativeLlamaEngine, reloading if model_path changed.
    """
    global _global_engine, _global_model_path

    if not model_path:
        return _global_engine

    if _global_engine is not None and _global_model_path == model_path and _global_engine.is_loaded():
        return _global_engine

    if os.path.exists(model_path):
        _global_model_path = model_path
        _global_engine = NativeLlamaEngine(
            model_path=model_path,
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
            temperature=temperature,
        )
        return _global_engine

    return None
