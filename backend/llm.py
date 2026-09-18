"""
Local LLM Service Wrapper
Supports loading local GGUF models via llama.cpp or connecting to OpenAI-compatible local endpoints,
integrating with the EmotionStreamProcessor for streaming dialogue.
"""

import json
import urllib.request
import urllib.error
from typing import Generator, Dict, Any, List, Optional
from backend.emotion import EmotionStreamProcessor


class LocalLLMEngine:
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
        """
        Checks if the local LLM server is accessible.
        """
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
        """
        Streams chat completion tokens from local endpoint,
        yielding sentence objects with emotion tags and 3D blendshapes as they complete.
        """
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
                                    "blendshapes": s["blendshapes"],
                                }
                            yield {
                                "type": "token",
                                "token": content,
                            }
                    except json.JSONDecodeError:
                        continue

            # Flush remaining buffer at stream completion
            final_sentences = processor.flush()
            for s in final_sentences:
                yield {
                    "type": "sentence",
                    "text": s["text"],
                    "emotion": s["emotion"],
                    "blendshapes": s["blendshapes"],
                }

        except urllib.error.URLError as e:
            # Server not currently running or reachable
            yield {
                "type": "error",
                "error": f"Failed to connect to local LLM at {self.api_base}: {e.reason}",
            }
