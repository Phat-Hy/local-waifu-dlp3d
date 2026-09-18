/**
 * Local AI Waifu Frontend Client (DLP3D / Babylon.js)
 * Coordinates 3D avatar rendering, real-time viseme lip-sync,
 * WebSocket chat streaming, and dynamic model & voice selection.
 */

// --- Global State ---
let scene, camera, engine;
let avatarMesh = null;
let morphTargets = {};
let ws = null;
let audioQueue = [];
let isPlayingAudio = false;
let audioContext = null;

const EMOTION_EMOJIS = {
  happy: "😊",
  smile: "😄",
  blush: "😳",
  shy: "🙈",
  tsundere: "😤",
  surprised: "😲",
  sad: "😢",
  thinking: "🤔",
  neutral: "🙂",
  angry: "😡",
  wink: "😉"
};

// --- DOM Elements ---
const canvas = document.getElementById("renderCanvas");
const statusPill = document.getElementById("status-pill");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const subtitleBox = document.getElementById("subtitle-box");
const subtitleText = document.getElementById("subtitle-text");
const emotionTag = document.getElementById("emotion-tag");
const settingsDrawer = document.getElementById("settings-drawer");
const openSettingsBtn = document.getElementById("open-settings-btn");
const closeSettingsBtn = document.getElementById("close-settings-btn");
const scanModelsBtn = document.getElementById("scan-models-btn");
const modelsList = document.getElementById("models-list");
const voicePathInput = document.getElementById("voice-path-input");
const setVoiceBtn = document.getElementById("set-voice-btn");
const voiceStatus = document.getElementById("voice-status");
const systemPromptInput = document.getElementById("system-prompt-input");
const savePromptBtn = document.getElementById("save-prompt-btn");

// --- 1. Initialize Babylon.js 3D Viewport ---
function initBabylon() {
  engine = new BABYLON.Engine(canvas, true);
  scene = new BABYLON.Scene(engine);
  scene.clearColor = new BABYLON.Color4(0.06, 0.07, 0.1, 1.0);

  // Camera focused on character's face & upper body
  camera = new BABYLON.ArcRotateCamera("Camera", -Math.PI / 2, Math.PI / 2.3, 3.2, new BABYLON.Vector3(0, 0.9, 0), scene);
  camera.attachControl(canvas, true);
  camera.lowerRadiusLimit = 1.5;
  camera.upperRadiusLimit = 6.0;

  // Soft anime lighting
  const hemiLight = new BABYLON.HemisphericLight("HemiLight", new BABYLON.Vector3(0, 1, 0), scene);
  hemiLight.intensity = 0.75;
  hemiLight.diffuse = new BABYLON.Color3(1, 0.95, 0.98);

  const dirLight = new BABYLON.DirectionalLight("DirLight", new BABYLON.Vector3(-1, -1, 1), scene);
  dirLight.intensity = 0.6;

  buildProceduralAvatar();

  engine.runRenderLoop(() => {
    scene.render();
  });

  window.addEventListener("resize", () => {
    engine.resize();
  });
}

// Procedural anime avatar head with real-time morph targets for visemes & expressions
function buildProceduralAvatar() {
  // Head sphere
  avatarMesh = BABYLON.MeshBuilder.CreateSphere("avatarHead", { diameter: 1.0, segments: 32 }, scene);
  avatarMesh.position.y = 1.0;

  const skinMat = new BABYLON.StandardMaterial("skinMat", scene);
  skinMat.diffuseColor = new BABYLON.Color3(1.0, 0.88, 0.82);
  skinMat.specularColor = new BABYLON.Color3(0.1, 0.1, 0.1);
  avatarMesh.material = skinMat;

  // Eyes
  const eyeMat = new BABYLON.StandardMaterial("eyeMat", scene);
  eyeMat.diffuseColor = new BABYLON.Color3(0.5, 0.2, 0.8);

  const leftEye = BABYLON.MeshBuilder.CreateSphere("leftEye", { diameterX: 0.18, diameterY: 0.24, diameterZ: 0.05 }, scene);
  leftEye.position = new BABYLON.Vector3(-0.2, 1.05, 0.45);
  leftEye.material = eyeMat;
  leftEye.parent = avatarMesh;

  const rightEye = BABYLON.MeshBuilder.CreateSphere("rightEye", { diameterX: 0.18, diameterY: 0.24, diameterZ: 0.05 }, scene);
  rightEye.position = new BABYLON.Vector3(0.2, 1.05, 0.45);
  rightEye.material = eyeMat;
  rightEye.parent = avatarMesh;

  // Mouth mesh for viseme lip-sync
  const mouthMat = new BABYLON.StandardMaterial("mouthMat", scene);
  mouthMat.diffuseColor = new BABYLON.Color3(0.85, 0.3, 0.4);

  const mouth = BABYLON.MeshBuilder.CreatePlane("mouth", { width: 0.16, height: 0.06 }, scene);
  mouth.position = new BABYLON.Vector3(0, 0.82, 0.49);
  mouth.material = mouthMat;
  mouth.parent = avatarMesh;

  // Hair bangs
  const hairMat = new BABYLON.StandardMaterial("hairMat", scene);
  hairMat.diffuseColor = new BABYLON.Color3(0.9, 0.35, 0.6);
  hairMat.specularColor = new BABYLON.Color3(0.2, 0.2, 0.2);

  const hair = BABYLON.MeshBuilder.CreateSphere("hair", { diameterX: 1.08, diameterY: 1.08, diameterZ: 1.05 }, scene);
  hair.position = new BABYLON.Vector3(0, 1.1, -0.05);
  hair.material = hairMat;
  hair.parent = avatarMesh;

  // Set references
  morphTargets = {
    mouthMesh: mouth,
    leftEye: leftEye,
    rightEye: rightEye,
    currentEmotion: "neutral",
  };

  // Subtle idle breathing animation
  scene.registerBeforeRender(() => {
    const time = performance.now() * 0.002;
    avatarMesh.position.y = 1.0 + Math.sin(time) * 0.015;
    avatarMesh.rotation.y = Math.sin(time * 0.5) * 0.04;
  });
}

// --- 2. Real-time Viseme Lip-Sync & Emotion Blendshapes ---
function applyVisemeFrame(frame) {
  if (!morphTargets.mouthMesh) return;
  const openness = frame.openness || 0;
  // Scale mouth plane based on viseme intensity
  const scaleY = Math.max(0.3, openness * 3.2);
  const scaleX = 1.0 + (frame.visemes?.aa || 0) * 0.8;
  morphTargets.mouthMesh.scaling.y = scaleY;
  morphTargets.mouthMesh.scaling.x = scaleX;
}

function applyEmotionBlendshape(emotion, blendshapes) {
  morphTargets.currentEmotion = emotion;

  // Update HUD badge
  const emoji = EMOTION_EMOJIS[emotion.toLowerCase()] || "🙂";
  emotionTag.querySelector(".emoji").textContent = emoji;
  emotionTag.querySelector(".label").textContent = emotion.toUpperCase();
  emotionTag.classList.remove("hidden");

  // Subtle head tilt on emotion
  if (emotion === "shy" || emotion === "blush") {
    avatarMesh.rotation.z = 0.06;
  } else if (emotion === "surprised") {
    avatarMesh.rotation.x = -0.05;
  } else {
    avatarMesh.rotation.z = 0;
    avatarMesh.rotation.x = 0;
  }
}

// --- 3. WebAudio Streaming Queue ---
function playNextAudioChunk() {
  if (audioQueue.length === 0) {
    isPlayingAudio = false;
    if (morphTargets.mouthMesh) {
      morphTargets.mouthMesh.scaling.y = 0.5;
      morphTargets.mouthMesh.scaling.x = 1.0;
    }
    return;
  }

  isPlayingAudio = true;
  const packet = audioQueue.shift();

  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
  }

  // Convert base64 WAV to ArrayBuffer
  const binaryString = atob(packet.audio_base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }

  audioContext.decodeAudioData(bytes.buffer, (audioBuffer) => {
    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);

    // Synchronize viseme timeline with audio playback
    const startTime = performance.now();
    const visemes = packet.visemes || [];

    const visemeInterval = setInterval(() => {
      const elapsedSec = (performance.now() - startTime) / 1000;
      if (elapsedSec > audioBuffer.duration) {
        clearInterval(visemeInterval);
        return;
      }
      // Find closest viseme frame
      const frame = visemes.find((f) => Math.abs(f.timestamp - elapsedSec) < 0.035);
      if (frame) {
        applyVisemeFrame(frame);
      }
    }, 30);

    source.onended = () => {
      clearInterval(visemeInterval);
      playNextAudioChunk();
    };

    source.start(0);
  });
}

// --- 4. WebSocket Streaming Connection ---
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.hostname || "127.0.0.1"}:18002/ws/chat`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    statusPill.className = "status-pill connected";
    statusPill.querySelector(".text").textContent = "Online";
  };

  ws.onclose = () => {
    statusPill.className = "status-pill disconnected";
    statusPill.querySelector(".text").textContent = "Reconnecting...";
    setTimeout(connectWebSocket, 2000);
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === "token") {
      subtitleBox.classList.remove("hidden");
      subtitleText.textContent += data.content;
    } else if (data.type === "audio_packet") {
      applyEmotionBlendshape(data.emotion, data.blendshapes);
      audioQueue.push(data);
      if (!isPlayingAudio) {
        playNextAudioChunk();
      }
    } else if (data.type === "done") {
      setTimeout(() => {
        // Keep subtitle visible for reading, fade out after a brief moment
      }, 3000);
    }
  };
}

// --- 5. Settings Drawer & Model/Voice Operations ---
async function fetchModels() {
  try {
    modelsList.innerHTML = `<div class="loading-spinner">Scanning directories...</div>`;
    const res = await fetch("/api/models");
    const data = await res.json();

    if (!data.models || data.models.length === 0) {
      modelsList.innerHTML = `<p class="desc" style="color: #ffab00;">No .gguf models found in configured scan folders.</p>`;
      return;
    }

    modelsList.innerHTML = "";
    data.models.forEach((m) => {
      const card = document.createElement("div");
      card.className = `model-card ${m.is_active ? "active" : ""}`;
      card.innerHTML = `
        <div class="title">${m.filename}</div>
        <div class="details">
          <span>Arch: ${m.architecture || "GGUF"}</span>
          <span>Ctx: ${m.context_length || "N/A"}</span>
          <span>Size: ${m.size_formatted}</span>
        </div>
      `;
      card.onclick = () => selectModel(m.path);
      modelsList.appendChild(card);
    });
  } catch (err) {
    modelsList.innerHTML = `<p class="desc" style="color: #ff5252;">Failed to load models: ${err.message}</p>`;
  }
}

async function selectModel(modelPath) {
  try {
    const res = await fetch("/api/models/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_path: modelPath }),
    });
    const data = await res.json();
    if (data.success) {
      fetchModels();
    }
  } catch (err) {
    alert("Error selecting model: " + err.message);
  }
}

async function applyVoice() {
  const path = voicePathInput.value.trim();
  if (!path) return;

  voiceStatus.className = "status-msg";
  voiceStatus.textContent = "Validating voice file...";

  try {
    const res = await fetch("/api/voice/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ voice_path: path }),
    });
    const data = await res.json();
    if (res.ok && data.success) {
      voiceStatus.className = "status-msg success";
      voiceStatus.textContent = `✓ Active voice reference set to: ${data.voice.filename}`;
    } else {
      voiceStatus.className = "status-msg error";
      voiceStatus.textContent = `✗ ${data.detail || "Validation failed"}`;
    }
  } catch (err) {
    voiceStatus.className = "status-msg error";
    voiceStatus.textContent = `✗ Error: ${err.message}`;
  }
}

async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    const cfg = await res.json();
    if (cfg.llm?.system_prompt) {
      systemPromptInput.value = cfg.llm.system_prompt;
    }
    if (cfg.tts?.active_voice_path) {
      voicePathInput.value = cfg.tts.active_voice_path;
    }
  } catch (e) {
    console.error("Config load error:", e);
  }
}

// --- 6. Event Listeners ---
chatForm.onsubmit = (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

  subtitleText.textContent = "";
  subtitleBox.classList.remove("hidden");
  ws.send(JSON.stringify({ text: text }));
  chatInput.value = "";
};

openSettingsBtn.onclick = () => {
  settingsDrawer.classList.remove("hidden");
  fetchModels();
  loadConfig();
};

closeSettingsBtn.onclick = () => {
  settingsDrawer.classList.add("hidden");
};

scanModelsBtn.onclick = fetchModels;
setVoiceBtn.onclick = applyVoice;

savePromptBtn.onclick = async () => {
  const prompt = systemPromptInput.value;
  await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ settings: { llm: { system_prompt: prompt } } }),
  });
  alert("System prompt saved!");
};

// --- Start Application ---
window.addEventListener("DOMContentLoaded", () => {
  initBabylon();
  connectWebSocket();
  loadConfig();
});
