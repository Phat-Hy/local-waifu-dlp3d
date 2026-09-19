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
import shutil
import zipfile
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


from backend.config import ConfigManager
from backend.scanner import scan_directory_for_models, validate_audio_file, parse_gguf_metadata, convert_audio_to_wav
from backend.emotion import EmotionStreamProcessor
from backend.tts import MockTTSClient, CosyVoiceTTSClient, F5TTSClient, get_tts_client, extract_audio_visemes
from backend.llm import get_llm_engine

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

# Initialize TTS Client (F5-TTS / CosyVoice / Edge-TTS)
tts_engine_name = config_mgr.get("tts", "engine", default="f5-tts")
preset_voice = config_mgr.get("tts", "voice_name", default="en-US-AnaNeural")
tts_client = get_tts_client(tts_engine_name, preset_voice)

# Initialize LLM Engine (Native GPU GGUF via llama_cpp)
active_model_path = config_mgr.get("llm", "active_model_path")
if not active_model_path or not os.path.exists(active_model_path):
    scan_dirs = config_mgr.get("llm", "scan_directories", default=["models"])
    scanned_models = scan_directory_for_models(scan_dirs)
    if scanned_models:
        active_model_path = scanned_models[0]["path"]
        config_mgr.set("llm", "active_model_path", active_model_path)

llm_engine = get_llm_engine(active_model_path) if active_model_path else None



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
    global llm_engine
    llm_engine = get_llm_engine(req.model_path)
    return {
        "success": True,
        "active_model": meta,
    }


@app.post("/api/voice/select")
async def select_voice(req: VoiceSelectRequest):
    """
    Validates and sets the user-chosen reference audio file (.wav, .flac, .mp3, etc.).
    Converts non-wav formats (like .flac) to PCM WAV automatically.
    """
    val = validate_audio_file(req.voice_path)
    if not val.get("valid"):
        raise HTTPException(status_code=400, detail=val.get("error", "Invalid audio file"))

    final_path = req.voice_path
    if not req.voice_path.lower().endswith(".wav"):
        try:
            final_path = convert_audio_to_wav(req.voice_path, destination_folder="voices")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to convert audio to WAV: {e}")

    config_mgr.set("tts", "active_voice_path", final_path)
    val["active_wav_path"] = final_path
    return {
        "success": True,
        "voice": val,
    }


@app.post("/api/voice/upload")
async def upload_voice(file: UploadFile = File(...)):
    """
    Accepts custom audio files uploaded from user's PC (.wav, .flac, .mp3, .ogg),
    saves to voices/ folder, and converts to WAV if needed.
    """
    valid_exts = (".wav", ".flac", ".mp3", ".ogg", ".m4a")
    if not file.filename.lower().endswith(valid_exts):
        raise HTTPException(status_code=400, detail="Supported audio formats: .wav, .flac, .mp3, .ogg")

    voices_dir = Path(__file__).parent.parent / "voices"
    voices_dir.mkdir(parents=True, exist_ok=True)
    temp_dest = voices_dir / file.filename

    with open(temp_dest, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    final_path = str(temp_dest)
    if not file.filename.lower().endswith(".wav"):
        try:
            final_path = convert_audio_to_wav(str(temp_dest), destination_folder=str(voices_dir))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to convert uploaded audio: {e}")

    config_mgr.set("tts", "active_voice_path", final_path)
    return {
        "success": True,
        "filename": Path(final_path).name,
        "path": final_path,
        "original_filename": file.filename,
    }



@app.get("/api/voice/presets")
async def get_voice_presets():
    """
    Returns available neural voice presets for Edge-TTS.
    """
    presets = [
        {"id": "en-US-AnaNeural", "name": "Ana (Anime / Sweet Girl - English)", "lang": "en"},
        {"id": "en-US-AvaNeural", "name": "Ava (Expressive / Friendly - English)", "lang": "en"},
        {"id": "en-US-EmmaNeural", "name": "Emma (Warm & Gentle - English)", "lang": "en"},
        {"id": "en-US-JennyNeural", "name": "Jenny (Youthful & Cheerful - English)", "lang": "en"},
        {"id": "ja-JP-NanamiNeural", "name": "Nanami (七海 - Anime Female - Japanese)", "lang": "ja"},
        {"id": "ja-JP-AoiNeural", "name": "Aoi (葵 - Energetic Female - Japanese)", "lang": "ja"},
        {"id": "ja-JP-KeitaNeural", "name": "Keita (圭太 - Male - Japanese)", "lang": "ja"},
        {"id": "en-US-GuyNeural", "name": "Guy (Male Companion - English)", "lang": "en"},
    ]
    active_voice = config_mgr.get("tts", "voice_name", default="en-US-AnaNeural")
    return {
        "presets": presets,
        "active_preset": active_voice
    }


@app.get("/api/config")
async def get_config():
    return config_mgr.config


@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest):
    for k, v in req.settings.items():
        if isinstance(v, dict) and k in config_mgr.config and isinstance(config_mgr.config[k], dict):
            config_mgr.config[k].update(v)
        else:
            config_mgr.config[k] = v
    config_mgr.save()

    # Update active TTS engine or fallback voice if changed
    if "tts" in req.settings and isinstance(req.settings["tts"], dict):
        global tts_client
        engine = config_mgr.get("tts", "engine", default="f5-tts")
        voice_name = config_mgr.get("tts", "voice_name", default="en-US-AnaNeural")
        tts_client = get_tts_client(engine, voice_name)

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
            "type": "glb",
            "description": desc,
            "size_mb": round(file_path.stat().st_size / (1024 * 1024), 1)
        })

    # Discover MMD (.pmx) models (like Hololive Shiori Novella)
    for file_path in chars_dir.rglob("*.pmx"):
        rel_path = file_path.relative_to(chars_dir).as_posix()
        char_name = file_path.stem
        if "shiori" in char_name.lower():
            char_name = "Shiori Novella (Hololive)"
            desc = "Hololive English -Advent- Official 3D Model"
        else:
            desc = "MMD / PMX 3D Character Model"

        available.append({
            "id": file_path.stem,
            "name": char_name,
            "file": rel_path,
            "type": "pmx",
            "description": desc,
            "size_mb": round(file_path.stat().st_size / (1024 * 1024), 1)
        })


    active_char = config_mgr.get("avatar", "character_file", default="FNN-default_296.glb")
    return {
        "characters": available,
        "active_character": active_char,
    }


@app.post("/api/characters/upload")
async def upload_character(file: UploadFile = File(...)):
    """
    Accepts custom 3D character models (.pmx, .pmd, .glb, .gltf) or .zip archives with textures.
    """
    filename_lower = file.filename.lower()
    valid_exts = (".glb", ".gltf", ".pmx", ".pmd", ".zip")
    if not filename_lower.endswith(valid_exts):
        raise HTTPException(status_code=400, detail="Only .pmx, .pmd, .glb, .gltf, or .zip packages are supported.")

    chars_dir = Path(__file__).parent.parent / "frontend" / "characters"
    chars_dir.mkdir(parents=True, exist_ok=True)

    if filename_lower.endswith(".zip"):
        zip_stem = Path(file.filename).stem
        dest_folder = chars_dir / zip_stem
        dest_folder.mkdir(parents=True, exist_ok=True)
        temp_zip = dest_folder / file.filename
        with open(temp_zip, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        try:
            with zipfile.ZipFile(temp_zip, "r") as zip_ref:
                zip_ref.extractall(dest_folder)
        finally:
            if temp_zip.exists():
                temp_zip.unlink()

        # Search for model file inside the extracted package (.pmx preferred for MMD, then .glb)
        candidates = (
            list(dest_folder.rglob("*.pmx")) +
            list(dest_folder.rglob("*.pmd")) +
            list(dest_folder.rglob("*.glb")) +
            list(dest_folder.rglob("*.gltf"))
        )
        if not candidates:
            raise HTTPException(status_code=400, detail="No .pmx, .pmd, or .glb 3D avatar found inside the zip archive.")

        chosen_file = candidates[0].relative_to(chars_dir).as_posix()
        config_mgr.set("avatar", "character_file", chosen_file)
        total_size = sum(f.stat().st_size for f in dest_folder.rglob("*") if f.is_file())
        return {
            "success": True,
            "filename": chosen_file,
            "size_mb": round(total_size / (1024 * 1024), 1)
        }
    else:
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


MOTION_METADATA = {
    "idle.vmd": ("Natural Idle & Breathing", "idle"),
    "talk.vmd": ("Conversational Talk & Gestures", "conversational"),
    "wave.vmd": ("Cute Wave", "gesture"),
    "bow.vmd": ("Formal Greeting Bow", "gesture"),
    "nod.vmd": ("Gentle Nod (Agree)", "gesture"),
    "thinking.vmd": ("Thinking & Head Tilt", "gesture"),
    "cheer.vmd": ("Cheer & Celebration", "gesture"),
    "drink.vmd": ("Drink (Hand to Mouth)", "gesture"),
    "swing_left.vmd": ("Left Arm Swing", "gesture"),
    "walk.vmd": ("Walk Locomotion", "action"),
    "sprint.vmd": ("Sprint / Run", "action"),
    "sneak.vmd": ("Sneak Posture", "action"),
    "tokino_dance.vmd": ("Tokino Dance", "dance"),
    "wavefile_dance.vmd": ("Wavefile Dance", "dance"),
    "heartbeat_dance.vmd": ("Heartbeat Dance", "dance"),
    "circulation_dance.vmd": ("Renai Circulation Dance", "dance"),
    "galaxy_dance.vmd": ("Galaxy Dance", "dance"),
    "neko_dance.vmd": ("Neko MMD Dance", "dance"),
    "elect_dance.vmd": ("Elect MMD Dance", "dance"),
    "shakeit_dance.vmd": ("Shake It Dance", "dance"),
}


@app.get("/api/motions")
async def list_motions():
    motions_dir = Path(__file__).parent.parent / "frontend" / "motions"
    motions_dir.mkdir(parents=True, exist_ok=True)
    motions = []
    category_order = {"idle": 0, "conversational": 1, "gesture": 2, "action": 3, "dance": 4, "custom": 5}
    for file_path in motions_dir.glob("*.vmd"):
        fname = file_path.name
        name, category = MOTION_METADATA.get(fname, (fname.replace(".vmd", "").replace("_", " ").title(), "custom"))
        motions.append({
            "id": file_path.stem,
            "name": name,
            "category": category,
            "filename": fname,
            "url": f"motions/{fname}",
            "size_kb": round(file_path.stat().st_size / 1024, 1)
        })
    motions.sort(key=lambda m: (category_order.get(m["category"], 9), m["name"]))
    return {"motions": motions}


@app.post("/api/motions/upload")
async def upload_motion(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".vmd"):
        raise HTTPException(status_code=400, detail="Only .vmd motion files are supported.")
    motions_dir = Path(__file__).parent.parent / "frontend" / "motions"
    motions_dir.mkdir(parents=True, exist_ok=True)
    destination = motions_dir / file.filename
    with open(destination, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {
        "success": True,
        "filename": file.filename,
        "url": f"motions/{file.filename}",
        "size_kb": round(destination.stat().st_size / 1024, 1)
    }


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





def formulate_contextual_dialogue(user_text: str) -> List[str]:
    txt = user_text.lower().strip()

    # 1. Greetings (hello, hi, hey, morning, evening, sup, yo)
    if any(w in txt for w in ["hello", "hi", "hey", "morning", "evening", "afternoon", "yo"]):
        return [
            "[happy][gesture:wave] Hello there! ",
            "It's so wonderful to hear from you today. ",
            "[smile][gesture:tilt] What exciting things shall we talk about?"
        ]

    # 2. Questions / Curiosity (why, what, how, who, when, where, ?, tell me, explain)
    elif any(w in txt for w in ["why", "what", "how", "who", "when", "where", "?", "tell me", "explain"]):
        return [
            "[thinking][gesture:think] Hmm, that is such an intriguing question! ",
            "[gesture:tilt] Let me ponder that for a moment... ",
            f"[smile][gesture:nod] Regarding '{user_text}', I think there are many fascinating secrets to uncover together!"
        ]

    # 3. Flattery / Affection / Compliments (cute, pretty, beautiful, love, marry, like you, sweet, best girl)
    elif any(w in txt for w in ["cute", "pretty", "beautiful", "love", "marry", "like you", "sweet", "adorable", "best girl"]):
        return [
            "[blush][gesture:shy] W-Wait, you're saying that so casually to my face?! ",
            "[tsundere] Don't think you can fluster me that easily... ",
            "[blush][gesture:tilt] But... thank you. You always know how to make my heart flutter."
        ]

    # 4. Praise / Gratitude (thank, thanks, awesome, great, amazing, good job, cool)
    elif any(w in txt for w in ["thank", "thanks", "awesome", "great", "amazing", "good job", "cool", "nice"]):
        return [
            "[happy][gesture:excited] Really?! ",
            "[smile][gesture:nod] Hearing that from you makes me so happy! ",
            "[gesture:wave] I'll keep doing my absolute best for you!"
        ]

    # 5. Empathy / Sadness / Tired (sad, tired, lonely, bad day, sigh, stressed, cry, hurt)
    elif any(w in txt for w in ["sad", "tired", "lonely", "bad day", "sigh", "stressed", "cry", "hurt", "depressed", "exhausted"]):
        return [
            "[sad][gesture:lean] Oh no... you've had a tough time, haven't you? ",
            "[smile] Please don't carry all that stress alone. ",
            "[blush][gesture:nod] I'm right here with you, and I'll keep you company until you feel better."
        ]

    # 6. Agreement / Affirmation (yes, yeah, right, agree, sure, ok, okay, absolutely)
    elif any(w in txt for w in ["yes", "yeah", "yep", "right", "agree", "sure", "ok", "okay", "exactly"]):
        return [
            "[smile][gesture:nod] Exactly! I couldn't agree more with you. ",
            "[happy][gesture:tilt] We really are on the same wavelength!"
        ]

    # 7. Disagreement / Playful Teasing (no, nope, stop, don't, disagree, wrong)
    elif any(w in txt for w in ["no", "nope", "stop", "don't", "disagree", "wrong"]):
        return [
            "[tsundere][gesture:shrug] Hmph! Is that so? ",
            "[smile][gesture:tilt] Well, maybe I enjoy teasing you just a little bit too much!"
        ]

    # 8. Natural Fallback Conversation
    else:
        return [
            f"[happy][gesture:nod] I heard you say: '{user_text}'. ",
            "[thinking][gesture:tilt] That definitely gives me something intriguing to think about. ",
            "[smile][gesture:wave] Tell me more, I'm all ears!"
        ]


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    Bidirectional streaming WebSocket endpoint.
    Feeds real-time audio chunks, visemes, gestures, and 3D blendshapes to the frontend.
    """
    await websocket.accept()
    conversation_history: List[Dict[str, str]] = []

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            user_text = msg.get("text", "")
            
            if not user_text.strip():
                continue

            prompt_voice = config_mgr.get("tts", "active_voice_path")
            system_prompt = config_mgr.get("llm", "system_prompt")
            conversation_history.append({"role": "user", "content": user_text})

            assistant_tokens: List[str] = []
            used_llm = False

            if llm_engine and llm_engine.is_loaded():
                try:
                    # Stream tokens & parsed sentences from real local LLM
                    for chunk in llm_engine.stream_chat(conversation_history[-8:], system_prompt=system_prompt):
                        c_type = chunk.get("type")
                        if c_type == "token":
                            tok = chunk["token"]
                            assistant_tokens.append(tok)
                            await websocket.send_json({"type": "token", "content": tok})
                        elif c_type == "sentence":
                            speakable_text = chunk["text"].strip()
                            if speakable_text:
                                wav_bytes = tts_client.synthesize(
                                    text=speakable_text,
                                    emotion=chunk["emotion"],
                                    voice_reference_path=prompt_voice,
                                )
                                visemes = extract_audio_visemes(wav_bytes)
                                audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
                            else:
                                audio_b64 = ""
                                visemes = []

                            await websocket.send_json({
                                "type": "audio_packet",
                                "text": speakable_text,
                                "emotion": chunk["emotion"],
                                "gesture": chunk.get("gesture", "none"),
                                "blendshapes": chunk["blendshapes"],
                                "visemes": visemes,
                                "audio_base64": audio_b64,
                                "format": "wav",
                            })
                        elif c_type == "error":
                            print(f"[LLM Engine] Stream error: {chunk.get('error')}")
                        await asyncio.sleep(0.01)

                    used_llm = True
                except Exception as e:
                    print(f"[WebSocket Chat] LLM streaming exception: {e}")
                    used_llm = False

            if not used_llm:
                # Fallback to rule-based contextual dialogue
                processor = EmotionStreamProcessor()
                dialogue_stream = formulate_contextual_dialogue(user_text)
                for token in dialogue_stream:
                    assistant_tokens.append(token)
                    await websocket.send_json({
                        "type": "token",
                        "content": token,
                    })
                    sentences = processor.process_token(token)
                    for s in sentences:
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
                            "gesture": s.get("gesture", "none"),
                            "blendshapes": s["blendshapes"],
                            "visemes": visemes,
                            "audio_base64": audio_b64,
                            "format": "wav",
                        })
                    await asyncio.sleep(0.04)

                for s in processor.flush():
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
                        "gesture": s.get("gesture", "none"),
                        "blendshapes": s["blendshapes"],
                        "visemes": visemes,
                        "audio_base64": audio_b64,
                        "format": "wav",
                    })

            # Record full response in conversation history
            full_reply = "".join(assistant_tokens).strip()
            if full_reply:
                conversation_history.append({"role": "assistant", "content": full_reply})

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
