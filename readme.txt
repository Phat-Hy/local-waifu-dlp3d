===============================================================================
                         LOCAL AI WAIFU (DLP3D)
===============================================================================

A fully local, zero-cloud, ultra-low-latency 3D AI companion engine featuring
MMD PMX physics, local GGUF LLM execution, zero-shot Flow-Matching voice cloning,
and real-time viseme lip-synchronization.

-------------------------------------------------------------------------------
1. OVERVIEW
-------------------------------------------------------------------------------
Local AI Waifu (DLP3D) is an offline companion engine designed to run entirely on
consumer hardware (e.g. an NVIDIA RTX 4060 Laptop GPU with 8GB VRAM). It brings
together local language model reasoning, real-time 3D animation, and instant
neural voice cloning so your companion speaks, gestures, and reacts naturally
without sending any data to external cloud servers.

Built upon the open-source foundations of DLP3D (Digital Life Project 2)
by dlp3d-ai: https://github.com/dlp3d-ai/dlp3d.ai

-------------------------------------------------------------------------------
2. KEY FEATURES
-------------------------------------------------------------------------------
* 3D Avatar & Biological Motion:
  - Full support for Hololive & MMD PMX character models via babylon-mmd.
  - Real-time physics for hair, skirts, ribbons, and accessories.
  - Procedural chest breathing, gentle weight shifting, neck articulation,
    and natural eye saccades with automatic blinks.
  - Quaternions-based calibrated A-pose with natural finger curls.
  - Forward-locked eye pupil focus preventing awkward slit-eye or cross-eyed
    distortions during smiling expressions.

* Local LLM Engine (GGUF via llama.cpp):
  - Direct CUDA GPU offloading of GGUF models (e.g., Qwen3.5-4B-Q4_K_M.gguf).
  - High generation throughput: 35-45 tokens per second.
  - Automatic model scanning across local directories.

* Ultra-Fast Voice Cloning (F5-TTS & CosyVoice):
  - Sub-second voice synthesis: ~0.3s - 0.6s per sentence (RTF 0.09 - 0.14).
  - Pristine 24kHz neural audio decoding powered by Vocos.
  - Zero prompt bleed: clean reference alignment eliminates prompt audio leaks.
  - Smooth fundamental frequency (F0) with tuned CFG guidance (1.8) and 12-step
    Euler integration, eliminating sudden high-pitch squeaks.
  - Zero-GPU fallback to Microsoft Edge-TTS when needed.

* Real-Time Lip-Sync & Emotion Parser:
  - Audio amplitude and formant analysis mapped directly to Japanese MMD
    vowels (A, I, U, E, O) and VRM/GLB visemes.
  - Automated extraction of emotion/gesture bracketed tags ([happy], [blush],
    [gesture:nod]) and non-verbal roleplay asterisks (*giggles*).
  - Automatic conversion of emojis into facial blendshapes.

* Reactive HUD & Status Badges:
  - "Thinking..." (pulsing amber beacon) when the LLM is pondering.
  - "Speaking" (live 3-bar green equalizer soundwave) during audio playback.
  - "Finished" (green checkmark transition) once speech is complete.
  - Instant speech interruption: typing a new message halts active speech.

-------------------------------------------------------------------------------
3. HARDWARE REQUIREMENTS
-------------------------------------------------------------------------------
* OS: Windows 10/11 (64-bit)
* GPU: NVIDIA GeForce RTX 3060, 4060, 4070 or better (6GB+ VRAM)
* CUDA: CUDA 12.1 or newer
* System Memory: 16 GB RAM minimum (32 GB recommended)
* Storage: 10 GB free space on SSD

-------------------------------------------------------------------------------
4. QUICK START (1-CLICK RUN)
-------------------------------------------------------------------------------
1. Clone the repository:
   git clone https://github.com/Phat-Hy/local-waifu-dlp3d.git
   cd local-waifu-dlp3d

2. Install Python dependencies:
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt

3. Setup F5-TTS environment (in services/f5-tts):
   cd services/f5-tts
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
   pip install f5-tts fastapi uvicorn soundfile
   python download_fast.py
   cd ../..

4. Start everything with one click:
   .\run.ps1

The launcher will start the F5-TTS microservice on port 50001, warm up the CUDA
kernels, launch the Waifu orchestrator on port 18002, and open your browser!

-------------------------------------------------------------------------------
5. DIRECTORY STRUCTURE
-------------------------------------------------------------------------------
├── backend/                  # Python backend orchestrator
│   ├── config.py             # Configuration manager
│   ├── emotion.py            # Emotion and gesture parser
│   ├── llm.py                # llama.cpp GGUF local model interface
│   ├── server.py             # FastAPI WebSocket and REST server
│   └── tts.py                # TTS service dispatcher
├── frontend/                 # WebGL 3D client application
│   ├── app.js                # Babylon.js scene and state machine
│   ├── index.html            # Web viewport and HUD
│   └── style.css             # UI styling
├── services/
│   ├── f5-tts/               # F5-TTS zero-shot voice cloning service (:50001)
│   └── cosyvoice/            # CosyVoice diffusion cloning service (:50000)
├── voices/                   # Reference voice audio clips
└── run.ps1                   # 1-Click launcher script

-------------------------------------------------------------------------------
6. ACKNOWLEDGEMENTS & UPSTREAM PROJECTS
-------------------------------------------------------------------------------
Special thanks to the authors and maintainers of the following open-source works:
- DLP3D (Digital Life Project 2): https://github.com/dlp3d-ai/dlp3d.ai
  Avatar rendering layout, blendshape viseme logic, and web client base.
- F5-TTS: https://github.com/SWivid/F5-TTS
  Flow Matching zero-shot speech synthesis engine.
- babylon-mmd: https://github.com/noname0310/babylon-mmd
  MMD .pmx model loader and Japanese morph runtime for Babylon.js.
- CosyVoice: https://github.com/FunAudioLLM/CosyVoice
  Multi-lingual speech generation research.
- llama.cpp / Ollama: https://github.com/ggerganov/llama.cpp
  High-performance local GGUF inference engine.
- Cover Corp / Hololive Production: https://hololivepro.com
  Character design and original MMD assets for Shiori Novella.

-------------------------------------------------------------------------------
7. LICENSE
-------------------------------------------------------------------------------
Released under the MIT License. Character models and voice materials belong to
their respective copyright holders (Cover Corp / Hololive Production).
===============================================================================
