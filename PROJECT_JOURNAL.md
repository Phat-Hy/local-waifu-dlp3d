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
| **STEP-004** | `2026-09-19T01:31:00+07:00` | Plan | Formulated `plans/001-local-waifu-architecture.md` & Journal tracking system | **Active** | `plan-init` |
| **STEP-005** | `TBD` | Build | Initialize core backend server & local model directory scanner | Pending Review | `build-backend-scanner` |
| **STEP-006** | `TBD` | Build | Integrate LLM inference engine for Qwen 3.5 4B GGUF with emotion tag streaming | Pending | `build-llm-engine` |
| **STEP-007** | `TBD` | Build | Integrate CosyVoice TTS pipeline with voice cloning & audio generation | Pending | `build-tts-cosyvoice` |
| **STEP-008** | `TBD` | Build | Setup DLP3D 3D Avatar frontend interface with real-time lip-sync (audio2face) & motion | Pending | `build-avatar-frontend` |
| **STEP-009** | `TBD` | Review | End-to-end integration test & review against acceptance criteria (`hs:code-review`) | Pending | `review-v1` |

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
