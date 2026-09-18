# Plan 001: Local AI Waifu Architecture & Implementation Plan

> **Tracking ID**: `STEP-004`  
> **Timestamp**: `2026-09-19T01:31:00+07:00`  
> **Skill Phase**: `hs:plan`  
> **Status**: Ready for Review  

---

## 1. Overview

This plan establishes a modular, privacy-preserving, local AI Waifu desktop application running on Windows. 
The system integrates:
1. **DLP3D (Digital Life Project 2)** for real-time 3D character rendering, facial animation (`audio2face`), and gesture/motion generation (`speech2motion`).
2. **Local LLM Engine**: Supporting `models--unsloth--Qwen3.5-4B-GGUF` (and dynamically scanning user model directories for other GGUF models).
3. **Local TTS Engine**: **CosyVoice** (or lightweight fallback during initial bringup) with support for emotion-infused speech and custom voice reference samples.
4. **Decoupled Architecture**: All AI intelligence (LLM streaming, emotion extraction, TTS audio synthesis, and animation viseme computation) runs via a local Python Orchestrator API (FastAPI + WebSockets). This guarantees that the current Web/Tauri 3D viewport can easily be migrated to Godot 4 or Unity in the future without touching the AI services.

---

## 2. System Architecture & Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                       FRONTEND LAYER                        │
│   (Current: Webview / Tauri / DLP3D Web App - Babylon.js)   │
│   (Future Interchangeable Target: Godot 4 / Unity)          │
│                                                             │
│   • 3D Avatar Viewport (VRM / GLB meshes, lighting, camera) │
│   • Lip-sync & Blendshape Driver (audio2face visemes)       │
│   • Motion & Pose Controller (speech2motion)                │
│   • Model Scanner & Settings UI (Select GGUF, Voice clone)  │
│   • Chat HUD & Audio Input/Output Controls                  │
└──────────────────────────────┬──────────────────────────────┘
                               │ WebSocket (Audio + Motion + Emotion Stream)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│             BACKEND ORCHESTRATION LAYER (Python)            │
│                                                             │
│  [1. Model Scanner & Hub Service]                           │
│      • Discovers local .gguf models                         │
│      • Discovers voice sample .wav reference files          │
│                                                             │
│  [2. Local LLM Service (llama.cpp / llama-cpp-python)]      │
│      • Loads selected GGUF (e.g. Qwen 3.5 4B)               │
│      • Streams tokens & extracts emotion tags in real-time  │
│                                                             │
│  [3. TTS & Voice Cloning Service (CosyVoice)]               │
│      • Emotion-conditioned speech synthesis                 │
│      • Zero-shot speaker cloning from 3s reference audio    │
│                                                             │
│  [4. Motion & LipSync Preprocessor]                         │
│      • Synchronizes phonemes/visemes with speech waveform   │
│      • Emits synchronized packet to Frontend                │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Concrete Implementation Steps

### Step 1: Project Scaffolding & Git Tracking Checkpoint
* Initialize project structure:
  * `backend/` — Python FastAPI server, model scanner, LLM engine, and TTS wrapper.
  * `frontend/` — 3D viewport, DLP3D client, and UI settings.
  * `models/` — Configuration references and voice sample references.
* Tag git checkpoint: `plan-init`.

### Step 2: Model Scanner & Configuration Service (`backend/scanner.py`, `backend/config.py`)
* Implement scanner capable of:
  * Searching user-configured model directories (e.g., custom paths) for `.gguf` files.
  * Reading GGUF header metadata (tensor architecture, context length, quant type).
  * Listing available models with clean JSON payload for the UI menu.
* Verification check: Unit test scanning directories and confirming model metadata extraction.

### Step 3: Local LLM Engine with Emotion Extraction (`backend/llm.py`)
* Wrap local GGUF loading using `llama-cpp-python` / `llama.cpp` server API.
* Implement structured prompt template:
  * Instructs Qwen to produce character dialogue with emotion markers (e.g. `[happy]`, `[blush]`, `[thoughtful]`).
  * Yields streaming response chunked by sentence/clause for low-latency TTS pipeline.
* Verification check: CLI test generating streamed text + emotion tags from local Qwen model.

### Step 4: CosyVoice TTS Pipeline (`backend/tts.py`)
* Integrate CosyVoice synthesis pipeline:
  * Takes text + emotion intensity tag.
  * Generates PCM/WAV audio stream.
  * Allows passing a reference audio clip (3-5 seconds `.wav`) to clone character voice.
* Verification check: Script generating a sample voice clip with emotional variation.

### Step 5: DLP3D Avatar Integration (`frontend/`)
* Adapt DLP3D Babylon.js avatar renderer to run locally.
* Connect WebSocket feed to backend orchestrator:
  * Receive audio packets -> play through WebAudio API.
  * Receive facial blendshapes (`audio2face`) -> drive mouth & facial expressions in sync.
  * Receive motion signals (`speech2motion`) -> trigger body gestures.
* Verification check: Avatar plays synchronized speech, lips move with audio, and emotional expression shifts.

### Step 6: Settings & Model Switching Menu
* Add UI overlay:
  * Model Selector: Dropdown showing discovered GGUF models.
  * Voice Selector / Uploader: Allows uploading/selecting reference voice sample.
  * Personality & System Prompt editor.
* Verification check: User can switch GGUF model in UI without restarting backend.

---

## 4. Completion Criteria & Quality Gates

| Gate | Requirement | Verification Method |
| :--- | :--- | :--- |
| **G1: Scanner** | Discovers `.gguf` files with metadata without freezing UI | Automated test against directory |
| **G2: LLM Stream** | Qwen generates responses with latency < 1.5s to first token | Benchmark script |
| **G3: Emotion** | System accurately parses emotion tags and maps to 3D blendshapes | Mock emotion payload test |
| **G4: LipSync** | Avatar mouth moves with voice audio within +/- 80ms sync | Visual observation & audio frame matching |
| **G5: Standalone** | 100% offline capability verified with network disconnected | Network-isolated test run |

---

## 5. Risk Assessment & Mitigations

* **Risk 1: High VRAM consumption when running LLM + CosyVoice + 3D rendering together.**
  * *Mitigation*: Qwen 3.5 4B GGUF at `Q4_K_M` uses ~3 GB VRAM. CosyVoice uses ~1.5–2 GB. 3D rendering uses ~500 MB. Total VRAM fits well within typical 6GB–8GB GPUs. If GPU memory is constrained, LLM can offload layers to CPU via `n_gpu_layers`.
* **Risk 2: Latency between user prompt and speech playback.**
  * *Mitigation*: Sentence-level streaming. As soon as the first complete sentence is generated by Qwen, CosyVoice begins synthesizing audio while Qwen continues generating the rest of the reply.
