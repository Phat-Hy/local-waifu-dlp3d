"""
Main Orchestrator Server for Local AI Waifu
Exposes REST and WebSocket endpoints for:
- Local GGUF Model scanning and dynamic switching
- User voice reference file selection (.wav)
- Configuration management
- Real-time streaming conversation with synchronized audio, visemes, and emotion blendshapes
"""

import os
import json
import base64
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import ConfigManager
from backend.scanner import scan_directory_for_models, validate_audio_file, parse_gguf_metadata
from backend.emotion import EmotionStreamProcessor
from backend.tts import MockTTSClient, CosyVoiceTTSClient, extract_audio_visemes

app = FastAPI(title="Local AI Waifu Orchestrator", version="1.0.0")

# Enable CORS for Next.js / Vite / Tauri / Godot clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

config_mgr = ConfigManager()

# Initialize TTS Client
tts_engine_name = config_mgr.get("tts", "engine", default="mock")
if tts_engine_name == "cosyvoice":
    tts_client = CosyVoiceTTSClient()
else:
    tts_client = MockTTSClient()


class ModelSelectRequest(BaseModel):
    model_path: str


class VoiceSelectRequest(BaseModel):
    voice_path: str


class ConfigUpdateRequest(BaseModel):
    settings: Dict[str, Any]


class ChatRequest(BaseModel):
    message: str
    system_prompt: Optional[str] = None


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "active_model": config_mgr.get("llm", "active_model_path"),
        "active_voice": config_mgr.get("tts", "active_voice_path"),
        "tts_engine": config_mgr.get("tts", "engine"),
    }


@app.get("/api/models")
async def list_models():
    """
    Scans configured model directories for .gguf files and extracts metadata.
    """
    scan_dirs = config_mgr.get("llm", "scan_directories", default=["models"])
    models = scan_directory_for_models(scan_dirs)
    active_path = config_mgr.get("llm", "active_model_path", default="")

    # Tag active model
    for m in models:
        m["is_active"] = (os.path.normpath(m["path"]) == os.path.normpath(active_path)) if active_path else False

    return {
        "scan_directories": scan_dirs,
        "models": models,
        "active_model_path": active_path,
    }


@app.post("/api/models/select")
async def select_model(req: ModelSelectRequest):
    """
    Sets the active GGUF model path after validation.
    """
    if not os.path.exists(req.model_path):
        raise HTTPException(status_code=400, detail=f"File not found: {req.model_path}")
    
    meta = parse_gguf_metadata(req.model_path)
    if not meta.get("valid"):
        raise HTTPException(status_code=400, detail=f"Invalid GGUF file: {meta.get('error')}")

    config_mgr.set("llm", "active_model_path", req.model_path)
    return {
        "success": True,
        "active_model": meta,
    }


@app.post("/api/voice/select")
async def select_voice(req: VoiceSelectRequest):
    """
    Validates and sets the user-chosen reference .wav file for voice cloning.
    """
    val = validate_audio_file(req.voice_path)
    if not val.get("valid"):
        raise HTTPException(status_code=400, detail=val.get("error", "Invalid audio file"))

    config_mgr.set("tts", "active_voice_path", req.voice_path)
    return {
        "success": True,
        "voice": val,
    }


@app.get("/api/config")
async def get_config():
    return config_mgr.config


@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest):
    for k, v in req.settings.items():
        config_mgr.config[k] = v
    config_mgr.save()
    return {"success": True, "config": config_mgr.config}


class CharacterSelectRequest(BaseModel):
    character_file: str


@app.get("/api/characters")
async def list_characters():
    chars_dir = Path(__file__).parent.parent / "frontend" / "characters"
    characters = [
        {"id": "FNN", "name": "Furina", "file": "FNN-default_296.glb", "description": "Fontaine Hydro Archon"},
        {"id": "HT", "name": "Hu Tao", "file": "HT-default_214.glb", "description": "77th Director of Wangsheng Funeral Parlor"},
        {"id": "KL", "name": "Klee", "file": "KL-default_214.glb", "description": "Spark Knight of the Knights of Favonius"},
        {"id": "KQ", "name": "Keqing", "file": "KQ-default_420.glb", "description": "Yuheng of the Liyue Qixing"},
        {"id": "NXD", "name": "Nahida", "file": "NXD-default_321.glb", "description": "Lesser Lord Kusanali"},
        {"id": "Ani", "name": "Ani", "file": "Ani-default_481.glb", "description": "DLP3D Original Anime Character"},
    ]
    
    # Check which files actually exist on disk
    available = []
    for c in characters:
        file_path = chars_dir / c["file"]
        if file_path.exists():
            c["size_mb"] = round(file_path.stat().st_size / (1024 * 1024), 1)
            available.append(c)

    active_char = config_mgr.get("avatar", "character_file", default="FNN-default_296.glb")
    return {
        "characters": available,
        "active_character": active_char,
    }


@app.post("/api/characters/select")
async def select_character(req: CharacterSelectRequest):
    chars_dir = Path(__file__).parent.parent / "frontend" / "characters"
    target = chars_dir / req.character_file
    if not target.exists() and req.character_file != "procedural":
        raise HTTPException(status_code=400, detail=f"Character model not found: {req.character_file}")
    
    config_mgr.set("avatar", "character_file", req.character_file)
    return {"success": True, "active_character": req.character_file}



@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    Bidirectional streaming WebSocket endpoint.
    Feeds real-time audio chunks, visemes, and 3D blendshapes to the frontend.
    """
    await websocket.accept()
    processor = EmotionStreamProcessor()

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            user_text = msg.get("text", "")
            
            if not user_text.strip():
                continue

            # Check if LLM endpoint or mock stream
            # For immediate responsive interaction, generate speech packets
            prompt_voice = config_mgr.get("tts", "active_voice_path")
            
            # Formulate response with emotion tags (using character rules)
            mock_dialogue_stream = [
                "[happy] Master, ",
                "I heard you say: '",
                user_text,
                "'! ",
                "[blush] I am so happy to chat with you today. ",
                "[smile] Is there anything else you would like to do?"
            ]

            for token in mock_dialogue_stream:
                # Send raw token for real-time text subtitle display
                await websocket.send_json({
                    "type": "token",
                    "content": token,
                })
                
                # Check if a sentence completed
                sentences = processor.process_token(token)
                for s in sentences:
                    # Synthesize audio for this sentence
                    wav_bytes = tts_client.synthesize(
                        text=s["text"],
                        emotion=s["emotion"],
                        voice_reference_path=prompt_voice,
                    )
                    
                    # Extract synchronized visemes (mouth openness + vowels)
                    visemes = extract_audio_visemes(wav_bytes)
                    audio_b64 = base64.b64encode(wav_bytes).decode("ascii")

                    # Emit complete multimodel packet
                    await websocket.send_json({
                        "type": "audio_packet",
                        "text": s["text"],
                        "emotion": s["emotion"],
                        "blendshapes": s["blendshapes"],
                        "visemes": visemes,
                        "audio_base64": audio_b64,
                        "format": "wav",
                    })

                await asyncio.sleep(0.04)

            # Flush any remaining text
            final_sentences = processor.flush()
            for s in final_sentences:
                wav_bytes = tts_client.synthesize(
                    text=s["text"],
                    emotion=s["emotion"],
                    voice_reference_path=prompt_voice,
                )
                visemes = extract_audio_visemes(wav_bytes)
                audio_b64 = base64.b64encode(wav_bytes).decode("ascii")

                await websocket.send_json({
                    "type": "audio_packet",
                    "text": s["text"],
                    "emotion": s["emotion"],
                    "blendshapes": s["blendshapes"],
                    "visemes": visemes,
                    "audio_base64": audio_b64,
                    "format": "wav",
                })

            # Stream completion sentinel
            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        pass


frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=18002)
