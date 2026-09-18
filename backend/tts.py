"""
TTS (Text-to-Speech) Service Layer
Provides unified interface for CosyVoice (local zero-shot voice cloning with emotions)
and Edge-TTS (lightweight zero-GPU fallback).
Includes viseme / amplitude lip-sync preprocessor.
"""

import os
import io
import math
import struct
import wave
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


class BaseTTSClient:
    def synthesize(
        self,
        text: str,
        emotion: str = "neutral",
        voice_reference_path: Optional[str] = None,
    ) -> bytes:
        raise NotImplementedError


class EdgeTTSClient(BaseTTSClient):
    """
    Microsoft Edge Neural TTS Client.
    Generates high-quality human/anime speech in real-time with pitch & emotion inflection.
    """
    def __init__(self, voice_name: str = "en-US-AnaNeural", rate: str = "+0%", pitch: str = "+0Hz"):
        self.voice_name = voice_name
        self.rate = rate
        self.pitch = pitch

    def synthesize(
        self,
        text: str,
        emotion: str = "neutral",
        voice_reference_path: Optional[str] = None,
    ) -> bytes:
        import asyncio
        import edge_tts
        import soundfile as sf
        import concurrent.futures

        # Adjust pitch and rate subtly by emotion
        pitch = self.pitch
        rate = self.rate
        if emotion in ["happy", "smile"]:
            pitch = "+4Hz"
            rate = "+4%"
        elif emotion in ["sad", "thinking"]:
            pitch = "-4Hz"
            rate = "-6%"
        elif emotion in ["surprised"]:
            pitch = "+8Hz"
        elif emotion in ["shy", "blush"]:
            pitch = "+3Hz"
            rate = "-3%"

        async def _synthesize():
            comm = edge_tts.Communicate(text, self.voice_name, rate=rate, pitch=pitch)
            mp3_bytes = b""
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    mp3_bytes += chunk["data"]
            return mp3_bytes

        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                mp3_data = executor.submit(lambda: asyncio.run(_synthesize())).result(timeout=10)

            if mp3_data:
                audio_data, sr = sf.read(io.BytesIO(mp3_data))
                out = io.BytesIO()
                sf.write(out, audio_data, sr, format="WAV", subtype="PCM_16")
                return out.getvalue()
        except Exception as e:
            print(f"[EdgeTTS] Warning: {e}")

        return generate_mock_speech_wav(text)


class CosyVoiceTTSClient(BaseTTSClient):
    """
    CosyVoice Client for zero-shot voice cloning with prompt audio and emotional inflection.
    Falls back to EdgeTTSClient (real neural speech) if local CosyVoice server is not running.
    """
    def __init__(self, api_url: str = "http://127.0.0.1:50000"):
        self.api_url = api_url.rstrip("/")
        self.fallback_tts = EdgeTTSClient()

    def synthesize(
        self,
        text: str,
        emotion: str = "neutral",
        voice_reference_path: Optional[str] = None,
    ) -> bytes:
        """
        Synthesizes speech using CosyVoice zero-shot cloning.
        If reference audio is provided, it clones that character's voice.
        """
        import urllib.request
        import urllib.error
        import json

        wav_path = voice_reference_path or ""
        if wav_path and not os.path.isabs(wav_path):
            wav_path = str(Path(wav_path).resolve())

        payload = {
            "tts_text": text,
            "prompt_text": "",
            "prompt_wav": wav_path,
            "emotion": emotion,
        }
        
        try:
            req = urllib.request.Request(
                f"{self.api_url}/inference_zero_shot",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=90) as response:
                audio_data = response.read()
                if audio_data and len(audio_data) > 100:
                    return audio_data
        except Exception as e:
            print(f"[CosyVoice Client] Notice (falling back to Edge-TTS): {e}")

        # Fall back to real neural anime voice instead of flat sine wave
        return self.fallback_tts.synthesize(text, emotion=emotion, voice_reference_path=voice_reference_path)



class MockTTSClient(BaseTTSClient):
    """
    Lightweight mock TTS for tests and offline development without heavy model weights.
    Generates a valid PCM WAV file scaled to the length of the text.
    """
    def synthesize(
        self,
        text: str,
        emotion: str = "neutral",
        voice_reference_path: Optional[str] = None,
    ) -> bytes:
        return generate_mock_speech_wav(text)


def generate_mock_speech_wav(text: str, sample_rate: int = 22050) -> bytes:
    """
    Creates a small, valid in-memory .wav file with soft modulated tone corresponding to text length.
    Useful for offline testing and verifying the audio-lip-sync pipeline.
    """
    duration = max(0.4, len(text) * 0.08)  # ~80ms per character
    num_samples = int(sample_rate * duration)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)

        samples = []
        for i in range(num_samples):
            t = float(i) / sample_rate
            # 220Hz gentle sine wave with subtle envelope
            envelope = math.sin(math.pi * (i / num_samples))
            val = int(32767.0 * 0.3 * envelope * math.sin(2.0 * math.pi * 220.0 * t))
            samples.append(struct.pack("<h", val))

        wf.writeframes(b"".join(samples))

    return buf.getvalue()


def extract_audio_visemes(wav_bytes: bytes, frame_rate: int = 30) -> List[Dict[str, Any]]:
    """
    Extracts timestamped viseme (lip-sync) intensity frames from audio bytes.
    Computes volume envelope mapped to mouth blendshapes ('aa', 'ih', 'ou', 'ee', 'oh').
    """
    viseme_frames: List[Dict[str, Any]] = []
    try:
        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, "rb") as wf:
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            rate = wf.getframerate()
            frames_count = wf.getnframes()
            raw_data = wf.readframes(frames_count)

        if sampwidth != 2:
            return viseme_frames

        total_samples = frames_count * channels
        samples_per_viseme_frame = int(rate / frame_rate) * channels

        for frame_idx in range(0, frames_count // int(rate / frame_rate)):
            start_sample = frame_idx * samples_per_viseme_frame
            end_sample = min(start_sample + samples_per_viseme_frame, total_samples)
            
            chunk = raw_data[start_sample * 2 : end_sample * 2]
            if not chunk:
                break

            # Calculate RMS amplitude
            unpacked = struct.unpack(f"<{len(chunk)//2}h", chunk)
            if not unpacked:
                rms = 0.0
            else:
                sq_sum = sum(s * s for s in unpacked)
                rms = math.sqrt(sq_sum / len(unpacked))

            # Normalize 0.0 to 1.0 mouth openness
            normalized = min(1.0, max(0.0, (rms - 300) / 3000.0))
            
            # Simple alternating vowel viseme modulation for natural speech motion
            t_sec = frame_idx / frame_rate
            vowel_cycle = int((t_sec * 6) % 3)
            
            viseme_frames.append({
                "timestamp": round(t_sec, 3),
                "openness": round(normalized, 3),
                "visemes": {
                    "aa": round(normalized * (0.8 if vowel_cycle == 0 else 0.2), 3),
                    "ih": round(normalized * (0.7 if vowel_cycle == 1 else 0.1), 3),
                    "ou": round(normalized * (0.6 if vowel_cycle == 2 else 0.1), 3),
                }
            })

    except Exception as e:
        print(f"[VisemeExtractor] Warning: {e}")

    return viseme_frames
