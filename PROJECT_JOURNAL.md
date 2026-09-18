# Local AI Waifu (DLP3D) — Project Journal & Progress Tracker

> **Repository**: [Phat-Hy/local-waifu-dlp3d](https://github.com/Phat-Hy/local-waifu-dlp3d)  
> **Workflow**: Harness Skills (`hs:brainstorm` ➔ `hs:plan` ➔ `hs:build` ➔ `hs:code-review` ➔ `hs:ship`)  
> **Architecture Foundation**: Web/Desktop Shell (Babylon.js / Three.js 3D Avatar) + Python Orchestration API (Qwen GGUF + CosyVoice TTS + Audio2Face/Motion)

---

## Progress Log

| Step ID | Timestamp (Local) | Phase | Summary / Milestones | Status | Git Checkpoint / Tag |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **STEP-001** | `2026-09-19T01:14:00+07:00` | Setup | Harness Skills (`hs`) installed into `.agents/` | **Completed** | `setup-harness` |
| **STEP-002** | `2026-09-19T01:27:00+07:00` | Fix | Resolved Windows subshell syntax in hooks, tools operational | **Completed** | `fix-hooks` |
| **STEP-003** | `2026-09-19T01:29:00+07:00` | Brainstorm | Selected DLP3D framework, local Qwen GGUF, CosyVoice, & modular API architecture | **Completed** | `brainstorm-done` |
| **STEP-004** | `2026-09-19T01:31:00+07:00` | Plan | Formulated `plans/001-local-waifu-architecture.md` & Journal tracking system | **Completed** | `plan-init` |
| **STEP-005** | `2026-09-19T01:36:00+07:00` | Build | Implemented backend directory scanner & GGUF header parser (`backend/scanner.py`, `backend/config.py`) | **Completed** | `build-scanner` |
| **STEP-006** | `2026-09-19T01:36:30+07:00` | Build | Implemented Emotion Parser & Sentence Streamer (`backend/emotion.py`, `backend/llm.py`) | **Completed** | `build-llm-engine` |
| **STEP-007** | `2026-09-19T01:37:00+07:00` | Build | Implemented TTS layer & Audio Viseme Lip-Sync Preprocessor (`backend/tts.py`) | **Completed** | `build-tts` |
| **STEP-008** | `2026-09-19T01:38:30+07:00` | Build | Implemented DLP3D Babylon.js 3D avatar viewport, WebAudio queue, & Settings Drawer (`frontend/`) | **Completed** | `build-frontend` |
| **STEP-009** | `2026-09-19T01:39:00+07:00` | Review | 14/14 automated unit & integration tests passing | **Completed** | `build-v1` |
| **STEP-010** | `2026-09-19T01:43:00+07:00` | Build | Added official DLP3D character models (Furina, Hu Tao, Klee, Keqing, Nahida, Ani), `/api/characters` selector, and favicon | **Completed** | `avatar-models-v1` |
| **STEP-011** | `2026-09-19T01:49:00+07:00` | Build | Implemented Character Personality & Emotion Auto-Generator via web search API (`backend/character_generator.py`) + UI search integration | **Completed** | `char-personality-gen-v1` |
| **STEP-012** | `2026-09-19T02:02:00+07:00` | Build | Integrated official Hololive MMD (`.pmx`) model support via `babylon-mmd` and installed Shiori Novella 3D avatar | **Completed** | `shiori-novella-support` |




---

## How to Backtrack (Rollback Guide)

Each milestone is associated with a Git commit and tag. If you ever need to roll back to a specific state or inspect prior code:

1. **View checkpoint history**:
   ```powershell
   git log --oneline --decorate --graph
   ```
2. **Backtrack to a specific Step**:
   ```powershell
   # Temporarily view or test a past step:
   git checkout <tag-name>    # e.g., git checkout plan-init

   # Or revert to a past step while keeping later work in a new branch:
   git switch -c rollback-step <tag-name>
   ```

---

## Architectural Decisions Record (ADR)

* **ADR-001 (Framework)**: Selected `dlp3d-ai` (Digital Life Project 2) as avatar foundation.
* **ADR-002 (Decoupled API)**: Backend provides an OpenAI-compatible / WebSocket streaming interface for LLM, TTS, emotion, and motion cues so the frontend (currently web/Tauri with 3D avatar) can be swapped for Godot 4 or Unity later with zero backend changes.
* **ADR-003 (TTS Engine)**: CosyVoice designated as primary local expressive TTS engine with zero-shot voice cloning capabilities.
* **ADR-004 (LLM Runtime)**: Local GGUF execution with automated directory scanning allowing dynamic model selection from UI.
