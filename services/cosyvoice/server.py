"""
CosyVoice Local Zero-Shot Inference Server
Listens on port 50000 to provide zero-shot voice cloning for Local AI Waifu.
"""

import os
import sys
import io
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="CosyVoice Zero-Shot Inference Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global model handle
cosyvoice_model = None
model_load_error = None

def init_model():
    global cosyvoice_model, model_load_error
    try:
        repo_path = Path(__file__).parent / "CosyVoice"
        if repo_path.exists() and str(repo_path) not in sys.path:
            sys.path.insert(0, str(repo_path))
        matcha_path = repo_path / "third_party" / "Matcha-TTS"
        if matcha_path.exists() and str(matcha_path) not in sys.path:
            sys.path.insert(0, str(matcha_path))
        import torch
        from cosyvoice.cli.cosyvoice import CosyVoice, CosyVoice2
        model_dir = Path(__file__).parent / "pretrained_models" / "CosyVoice-300M"
        if not model_dir.exists():
            # Check for alternative model directories
            candidates = list((Path(__file__).parent / "pretrained_models").glob("*CosyVoice*"))
            if candidates:
                model_dir = candidates[0]

        if model_dir.exists():
            print(f"[CosyVoice Server] Loading model from {model_dir} on CUDA: {torch.cuda.is_available()} (fp16=True)...")
            cosyvoice_model = CosyVoice(str(model_dir), fp16=True)
            print("[CosyVoice Server] Model successfully loaded with fp16 acceleration.")
        else:
            model_load_error = f"Model weights not found in {model_dir}. Please run setup_cosyvoice.ps1."
            print(f"[CosyVoice Server] {model_load_error}")
    except Exception as e:
        model_load_error = str(e)
        print(f"[CosyVoice Server] Warning during initialization: {e}")


class ZeroShotRequest(BaseModel):
    tts_text: str
    prompt_text: Optional[str] = ""
    prompt_wav: str
    emotion: Optional[str] = "neutral"


@app.get("/health")
async def health():
    has_torch = False
    cuda_available = False
    try:
        import torch
        has_torch = True
        cuda_available = torch.cuda.is_available()
    except ImportError:
        pass

    return {
        "status": "online",
        "service": "cosyvoice",
        "has_torch": has_torch,
        "cuda_available": cuda_available,
        "model_loaded": cosyvoice_model is not None,
        "error": model_load_error,
    }


_prompt_cache = {}

def get_cached_prompt_features(prompt_path: str):
    """
    Caches the Whisper mel spectrogram, ONNX speech tokenizer tokens, and CampPlus speaker embedding.
    Saves ~1.5s - 2.0s of redundant disk and ONNX overhead on every single sentence request.
    """
    global _prompt_cache
    if prompt_path in _prompt_cache:
        return _prompt_cache[prompt_path]

    f = cosyvoice_model.frontend
    speech_feat, speech_feat_len = f._extract_speech_feat(prompt_path)
    speech_token, speech_token_len = f._extract_speech_token(prompt_path)
    embedding = f._extract_spk_embedding(prompt_path)
    
    _prompt_cache[prompt_path] = (
        speech_feat, speech_feat_len,
        speech_token, speech_token_len,
        embedding
    )
    return _prompt_cache[prompt_path]


@app.post("/inference_zero_shot")
async def inference_zero_shot(req: ZeroShotRequest):
    """
    Executes zero-shot voice cloning using the provided reference wav audio.
    """
    global cosyvoice_model
    if not req.tts_text.strip():
        raise HTTPException(status_code=400, detail="Text is required")

    prompt_path = req.prompt_wav
    # CosyVoice golden sweet-spot prompt length is 4.0s - 5.0s
    # Shorter prompt drastically cuts transformer cross-attention matrix from 300 to ~100 tokens, 2x-3x speedup!
    try:
        import soundfile as sf
        info = sf.info(prompt_path)
        if info.duration > 5.5:
            trimmed_name = f"trimmed_5s_{Path(prompt_path).stem[:24]}.wav"
            trimmed_path = str(Path(prompt_path).parent / trimmed_name)
            if not os.path.exists(trimmed_path):
                data, sr = sf.read(prompt_path)
                sf.write(trimmed_path, data[:sr * 5], sr)
            prompt_path = trimmed_path
    except Exception as e:
        print(f"[CosyVoice Server] Notice during audio inspection: {e}")

    try:
        import torch
        import torchaudio

        audio_chunks = []

        # If prompt_text is provided, use zero-shot; otherwise high-speed cached cross-lingual
        if req.prompt_text and req.prompt_text.strip():
            output_generator = cosyvoice_model.inference_zero_shot(
                req.tts_text,
                req.prompt_text.strip(),
                prompt_path,
                stream=False
            )
            for chunk in output_generator:
                audio_chunks.append(chunk["tts_speech"])
        else:
            # High-speed cached inference: bypasses repeated mel/token/embedding extraction
            speech_feat, speech_feat_len, speech_token, speech_token_len, embedding = get_cached_prompt_features(prompt_path)
            f = cosyvoice_model.frontend
            
            for i in f.text_normalize(req.tts_text, split=True, text_frontend=True):
                tts_text_token, tts_text_token_len = f._extract_text_token(i)
                model_input = {
                    'text': tts_text_token,
                    'text_len': tts_text_token_len,
                    'prompt_text': torch.zeros(1, 0, dtype=torch.int32).to(f.device),
                    'prompt_text_len': torch.zeros(1, dtype=torch.int32).to(f.device),
                    'llm_prompt_speech_token': speech_token,
                    'llm_prompt_speech_token_len': speech_token_len,
                    'flow_prompt_speech_token': speech_token,
                    'flow_prompt_speech_token_len': speech_token_len,
                    'prompt_speech_feat': speech_feat,
                    'prompt_speech_feat_len': speech_feat_len,
                    'llm_embedding': embedding,
                    'flow_embedding': embedding,
                }
                for model_output in cosyvoice_model.model.tts(**model_input, stream=False, speed=1.0):
                    audio_chunks.append(model_output["tts_speech"])

        if not audio_chunks:
            raise HTTPException(status_code=500, detail="No audio was generated by CosyVoice.")

        full_speech = torch.concat(audio_chunks, dim=1)
        
        # Write to WAV buffer
        buf = io.BytesIO()
        torchaudio.save(buf, full_speech, cosyvoice_model.sample_rate, format="wav")
        wav_bytes = buf.getvalue()

        return Response(content=wav_bytes, media_type="audio/wav")

    except Exception as e:
        print(f"[CosyVoice Server] Inference error: {e}")
        raise HTTPException(status_code=500, detail=f"Synthesis error: {str(e)}")


if __name__ == "__main__":
    init_model()
    uvicorn.run(app, host="127.0.0.1", port=50000)
