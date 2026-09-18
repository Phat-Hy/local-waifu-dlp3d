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
    chars_dir.mkdir(parents=True, exist_ok=True)

    KNOWN_INFO = {
        "FNN-default_296.glb": ("Furina", "Fontaine Hydro Archon"),
        "HT-default_214.glb": ("Hu Tao", "77th Director of Wangsheng Funeral Parlor"),
        "KL-default_214.glb": ("Klee", "Spark Knight of the Knights of Favonius"),
        "KQ-default_420.glb": ("Keqing", "Yuheng of the Liyue Qixing"),
        "NXD-default_321.glb": ("Nahida", "Lesser Lord Kusanali"),
        "Ani-default_481.glb": ("Ani", "DLP3D Original Anime Character"),
    }
    
    available = []
    for file_path in chars_dir.glob("*.glb"):
        fname = file_path.name
        name, desc = KNOWN_INFO.get(fname, (file_path.stem, "Custom 3D Character Model"))
        available.append({
            "id": file_path.stem,
            "name": name,
            "file": fname,
            "description": desc,
            "size_mb": round(file_path.stat().st_size / (1024 * 1024), 1)
        })

    active_char = config_mgr.get("avatar", "character_file", default="FNN-default_296.glb")
    return {
        "characters": available,
        "active_character": active_char,
    }


from fastapi import UploadFile, File
import shutil

@app.post("/api/characters/upload")
async def upload_character(file: UploadFile = File(...)):
    """
    Accepts custom .glb 3D character models uploaded through the UI.
    """
    if not file.filename.lower().endswith((".glb", ".gltf")):
        raise HTTPException(status_code=400, detail="Only .glb or .gltf 3D avatar files are supported.")

    chars_dir = Path(__file__).parent.parent / "frontend" / "characters"
    chars_dir.mkdir(parents=True, exist_ok=True)
    destination = chars_dir / file.filename

    with open(destination, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    config_mgr.set("avatar", "character_file", file.filename)
    return {
        "success": True,
        "filename": file.filename,
        "size_mb": round(destination.stat().st_size / (1024 * 1024), 1)
    }


@app.post("/api/characters/select")
async def select_character(req: CharacterSelectRequest):
    chars_dir = Path(__file__).parent.parent / "frontend" / "characters"
    target = chars_dir / req.character_file
    if not target.exists() and req.character_file != "procedural":
        raise HTTPException(status_code=400, detail=f"Character model not found: {req.character_file}")
    
    config_mgr.set("avatar", "character_file", req.character_file)
    return {"success": True, "active_character": req.character_file}


from backend.character_generator import generate_character_personality


class CharacterPersonalityRequest(BaseModel):
    character_name: str


@app.post("/api/character/generate_personality")
async def api_generate_personality(req: CharacterPersonalityRequest):
    """
    Searches online knowledge for character personality/lore and builds a 3D avatar system prompt.
    """
    result = generate_character_personality(req.character_name)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Generation failed"))

    # Auto-save generated prompt into active config
    config_mgr.set("llm", "system_prompt", result["system_prompt"])
    return result





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
