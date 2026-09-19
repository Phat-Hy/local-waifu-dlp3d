"""
F5-TTS Local Zero-Shot Inference Server
Listens on port 50001 to provide ultra-fast Flow-Matching voice cloning for Local AI Waifu.
"""

import os
import sys
import io
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
import soundfile as sf
import uvicorn

app = FastAPI(title="F5-TTS Zero-Shot Inference Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global model handle
f5_model = None
model_load_error = None

# Known reference transcripts for characters
KNOWN_PROMPTS = {
    "shiori_reference_calm": "Of course you have to read one too. Everyone has a few flaws they need to work on.",
    "candidate_calm": "Of course you have to read one too. Everyone has a few flaws they need to work on.",
    "shiori_reference_clean": "Oh hey glad you're here. Come in and take a seat.",
    "shiori": "Of course you have to read one too. Everyone has a few flaws they need to work on.",
}

DEFAULT_CHECKPOINT = Path(__file__).parent / "checkpoints" / "model_1250000.safetensors"


def init_model():
    global f5_model, model_load_error
    try:
        import torch
        from f5_tts.api import F5TTS

        ckpt_path = str(DEFAULT_CHECKPOINT.resolve())
        if not DEFAULT_CHECKPOINT.exists() or DEFAULT_CHECKPOINT.stat().st_size < 1348000000:
            model_load_error = f"Checkpoint file missing or incomplete at {ckpt_path}"
            print(f"[F5-TTS Server] {model_load_error}")
            return

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[F5-TTS Server] Initializing F5TTS on {device} (CUDA device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None'})...")
        t0 = time.time()
        f5_model = F5TTS(
            model="F5TTS_v1_Base",
            ckpt_file=ckpt_path,
            ode_method="euler",
            device=device,
        )
        print(f"[F5-TTS Server] Loaded model in {time.time() - t0:.2f}s! Ready for flow-matching inference.")

        # Warm up PyTorch CUDA kernels so first user interaction is instant
        voices_dir = Path(__file__).resolve().parent.parent.parent / "voices"
        default_shiori = voices_dir / "shiori_reference_calm.wav"
        if not default_shiori.exists():
            default_shiori = voices_dir / "shiori_reference_clean.wav"
        if not default_shiori.exists():
            default_shiori = voices_dir / "shiori_prompt_12s.wav"

        if default_shiori.exists():
            print("[F5-TTS Server] Running GPU kernel warmup...")
            prompt_text = KNOWN_PROMPTS.get("shiori_reference_calm") if "calm" in str(default_shiori) else "Oh hey glad you're here. Come in and take a seat."
            with torch.inference_mode():
                f5_model.infer(
                    ref_file=str(default_shiori),
                    ref_text=prompt_text,
                    gen_text="Ready!",
                    nfe_step=8,
                )
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            print("[F5-TTS Server] Warmup complete! Zero first-interaction cold start.")

    except Exception as e:
        model_load_error = str(e)
        print(f"[F5-TTS Server] Initialization error: {e}")


class ZeroShotRequest(BaseModel):
    tts_text: str
    prompt_text: Optional[str] = ""
    prompt_wav: Optional[str] = ""
    emotion: Optional[str] = "neutral"
    speed: Optional[float] = 1.0
    nfe_step: Optional[int] = 8


@app.get("/health")
async def health():
    has_torch = False
    cuda_available = False
    device_name = ""
    try:
        import torch
        has_torch = True
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            device_name = torch.cuda.get_device_name(0)
    except ImportError:
        pass

    return {
        "status": "online",
        "service": "f5-tts",
        "has_torch": has_torch,
        "cuda_available": cuda_available,
        "device_name": device_name,
        "model_loaded": f5_model is not None,
        "error": model_load_error,
    }


@app.post("/inference_zero_shot")
async def inference_zero_shot(req: ZeroShotRequest):
    """
    Executes high-speed flow-matching zero-shot voice cloning using F5-TTS.
    """
    global f5_model
    if f5_model is None:
        raise HTTPException(status_code=503, detail=f"F5-TTS model not initialized: {model_load_error}")

    import re
    import numpy as np

    raw_text = req.tts_text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="Text is required")

    # Strip emojis and non-alphanumeric / non-punctuation characters that crash vocoder/Windows charmap
    clean_text = re.sub(r"[\U00010000-\U0010ffff]", "", raw_text)
    clean_text = re.sub(r"[^\w\s.,!?;:\'\"\-]", " ", clean_text)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()

    # If text has no alphanumeric characters (e.g. only punctuation, emoji or empty), return short clean silence
    if not re.search(r"\w+", clean_text):
        sr = 24000
        silence_wav = np.zeros(int(sr * 0.1), dtype=np.int16)
        buf = io.BytesIO()
        sf.write(buf, silence_wav, sr, format="WAV", subtype="PCM_16")
        return Response(content=buf.getvalue(), media_type="audio/wav")

    # Locate prompt audio
    prompt_path = req.prompt_wav or ""
    voices_dir = Path(__file__).resolve().parent.parent.parent / "voices"
    default_shiori = voices_dir / "shiori_reference_calm.wav"
    if not default_shiori.exists():
        default_shiori = voices_dir / "shiori_reference_clean.wav"
    if not default_shiori.exists():
        default_shiori = voices_dir / "shiori_prompt_12s.wav"

    # Automatically redirect any legacy or old prompt requests to the calm reference
    p_lower = (prompt_path or "").lower()
    if not prompt_path or not os.path.exists(prompt_path) or "shiori_prompt_12s" in p_lower:
        if default_shiori.exists():
            prompt_path = str(default_shiori)
        elif os.path.exists(prompt_path):
            pass
        else:
            raise HTTPException(status_code=400, detail="No reference audio found")

    prompt_text = (req.prompt_text or "").strip()
    if not prompt_text:
        # Check known prompts
        p_lower = prompt_path.lower()
        for key, val in KNOWN_PROMPTS.items():
            if key in p_lower:
                prompt_text = val
                break
        if not prompt_text:
            prompt_text = "Of course you have to read one too. Everyone has a few flaws they need to work on."

    try:
        import torch
        t0 = time.time()
        nfe = req.nfe_step if req.nfe_step and req.nfe_step in [8, 12, 16, 24, 32] else 12
        speed = req.speed if req.speed and 0.5 <= req.speed <= 2.0 else 1.0

        with torch.inference_mode():
            wav, sr, _ = f5_model.infer(
                ref_file=prompt_path,
                ref_text=prompt_text,
                gen_text=clean_text,
                nfe_step=nfe,
                cfg_strength=1.8,
                speed=speed,
            )

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        gen_time = time.time() - t0
        audio_dur = len(wav) / sr if sr > 0 else 0
        rtf = gen_time / audio_dur if audio_dur > 0 else 0
        print(f"[F5-TTS Server] Generated {audio_dur:.2f}s audio in {gen_time:.2f}s (RTF: {rtf:.2f}, nfe={nfe})")

        # Encode to WAV buffer
        buf = io.BytesIO()
        sf.write(buf, wav, sr, format="WAV", subtype="PCM_16")
        wav_bytes = buf.getvalue()

        return Response(content=wav_bytes, media_type="audio/wav")

    except Exception as e:
        print(f"[F5-TTS Server] Inference error: {e}")
        raise HTTPException(status_code=500, detail=f"Synthesis error: {str(e)}")


if __name__ == "__main__":
    init_model()
    uvicorn.run(app, host="127.0.0.1", port=50001)
