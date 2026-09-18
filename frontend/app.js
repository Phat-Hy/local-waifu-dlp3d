/**
 * Local AI Waifu Frontend Client (DLP3D / Babylon.js)
 * Coordinates 3D avatar rendering, real-time viseme lip-sync,
 * WebSocket chat streaming, and dynamic model, voice & character selection.
 */

// --- Global State ---
let scene, camera, engine;
let avatarMesh = null;
let loadedGlbMeshes = [];
let activeMorphTargets = {};
let activeMorphTargetManager = null;
let activeBones = { spine: null, chest: null, neck: null, head: null, leftArm: null, rightArm: null };
let currentAnimationGroups = [];
let currentCharacterFile = null;
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
const charactersList = document.getElementById("characters-list");
const scanModelsBtn = document.getElementById("scan-models-btn");
const modelsList = document.getElementById("models-list");
const voicePathInput = document.getElementById("voice-path-input");
const setVoiceBtn = document.getElementById("set-voice-btn");
const voiceStatus = document.getElementById("voice-status");
const voicePresetSelect = document.getElementById("voice-preset-select");
const systemPromptInput = document.getElementById("system-prompt-input");
const savePromptBtn = document.getElementById("save-prompt-btn");
const camFaceBtn = document.getElementById("cam-face-btn");
const camBodyBtn = document.getElementById("cam-body-btn");
const testBlinkBtn = document.getElementById("test-blink-btn");

if (camFaceBtn) {
  camFaceBtn.onclick = () => {
    camera.setTarget(new BABYLON.Vector3(0, 1.35, 0));
    camera.radius = 1.9;
  };
}

if (camBodyBtn) {
  camBodyBtn.onclick = () => {
    camera.setTarget(new BABYLON.Vector3(0, 0.85, 0));
    camera.radius = 3.6;
  };
}

function triggerManualBlink() {
  const start = performance.now();
  const duration = 240; // 240ms visible smooth blink
  const animate = (now) => {
    const elapsed = now - start;
    if (elapsed < duration) {
      const weight = Math.sin((elapsed / duration) * Math.PI);
      setMorphInfluence(["まばたき", "blink", "eye_blink", "eyeblink"], weight);
      requestAnimationFrame(animate);
    } else {
      setMorphInfluence(["まばたき", "blink", "eye_blink", "eyeblink"], 0);
    }
  };
  requestAnimationFrame(animate);
}

if (testBlinkBtn) {
  testBlinkBtn.onclick = () => {
    triggerManualBlink();
  };
}


// --- 1. Initialize Babylon.js 3D Viewport ---
function initBabylon() {
  engine = new BABYLON.Engine(canvas, true);
  scene = new BABYLON.Scene(engine);
  scene.clearColor = new BABYLON.Color4(0.06, 0.07, 0.1, 1.0);

  // Camera focused on character's face & upper body
  camera = new BABYLON.ArcRotateCamera("Camera", -Math.PI / 2, Math.PI / 2.2, 2.5, new BABYLON.Vector3(0, 1.35, 0), scene);
  camera.attachControl(canvas, true);
  camera.lowerRadiusLimit = 0.5;
  camera.upperRadiusLimit = 25.0;
  camera.wheelPrecision = 40;
  camera.panningSensibility = 800; // Right-click or Ctrl+drag to pan anywhere smoothly

  // Soft anime lighting
  const hemiLight = new BABYLON.HemisphericLight("HemiLight", new BABYLON.Vector3(0, 1, 0), scene);
  hemiLight.intensity = 0.85;
  hemiLight.diffuse = new BABYLON.Color3(1, 0.96, 0.98);

  const dirLight = new BABYLON.DirectionalLight("DirLight", new BABYLON.Vector3(-1, -1, 1), scene);
  dirLight.intensity = 0.7;

  // Initial character load
  loadCharacterModel("FNN-default_296.glb");

  // Procedural idle breathing, micro-swaying, dynamic conversation gestures & auto-blink loop
  let animTime = 0;
  let lastBlink = 0;
  let nextBlink = 3.5;
  const blinkDuration = 0.24;

  let currentGesture = {
    name: "none",
    startTime: 0,
    duration: 1.5
  };

  window.triggerGesture = function(gestureName) {
    if (!gestureName || gestureName === "none") return;
    console.log(`[Avatar] Conversation Gesture Triggered: ${gestureName}`);
    currentGesture = {
      name: gestureName.toLowerCase().trim(),
      startTime: animTime,
      duration: gestureName === "wave" ? 2.5 : (gestureName === "excited" ? 1.9 : 1.7)
    };
  };

  scene.onBeforeRenderObservable.add(() => {
    const dt = engine.getDeltaTime() / 1000.0;
    animTime += dt;

    // 1. Natural Breathing & Spine Sway (Base idle layer)
    if (activeBones.chest || activeBones.spine) {
      const breath = Math.sin(animTime * 1.8) * 0.012;
      const sway = Math.cos(animTime * 0.75) * 0.008;
      const bone = activeBones.chest || activeBones.spine;
      bone.rotation = new BABYLON.Vector3(breath, sway, 0);
    }

    // 2. Subtle Head Tilt & Nodding (Speech cadence)
    if (activeBones.head) {
      const speakingMod = isPlayingAudio ? 2.5 : 1.0;
      const headNod = Math.sin(animTime * (isPlayingAudio ? 4.2 : 1.1)) * (0.014 * speakingMod);
      const headTilt = Math.cos(animTime * 0.65) * 0.01;
      activeBones.head.rotation = new BABYLON.Vector3(headNod, 0, headTilt);
    }

    // 3. Natural Arm Rest & Sway
    if (activeBones.leftArm) {
      activeBones.leftArm.rotation = new BABYLON.Vector3(0, 0, -0.92 + Math.sin(animTime * 1.8) * 0.01);
    }
    if (activeBones.rightArm) {
      activeBones.rightArm.rotation = new BABYLON.Vector3(0, 0, 0.92 - Math.sin(animTime * 1.8) * 0.01);
    }

    // 4. Dynamic Conversational Gesture Engine (Driven by what the user says!)
    if (currentGesture.name !== "none") {
      const gElapsed = animTime - currentGesture.startTime;
      const gDuration = currentGesture.duration;

      if (gElapsed < gDuration) {
        const p = gElapsed / gDuration; // 0.0 -> 1.0 (smooth gesture curve)

        // Wave: Greets user, arm raises and waves hand
        if (currentGesture.name === "wave" && activeBones.rightArm) {
          const armHeight = -0.4 - Math.sin(p * Math.PI) * 0.78;
          const handWave = Math.sin(p * 20.0) * 0.28;
          activeBones.rightArm.rotation = new BABYLON.Vector3(0, handWave, armHeight);
          if (activeBones.head) activeBones.head.rotation = new BABYLON.Vector3(-0.02, -0.04, 0.03);
        }
        // Nod: Agrees emphatically with user
        else if (currentGesture.name === "nod" && activeBones.head) {
          const nodPitch = Math.sin(p * 12.0) * 0.055 * (1.0 - p * 0.4);
          activeBones.head.rotation = new BABYLON.Vector3(nodPitch, 0, 0);
          if (activeBones.chest) activeBones.chest.rotation = new BABYLON.Vector3(nodPitch * 0.35, 0, 0);
        }
        // Tilt: Inquisitive, curious head tilt
        else if (currentGesture.name === "tilt" && activeBones.head) {
          const tiltRoll = Math.sin(p * Math.PI) * 0.09;
          activeBones.head.rotation = new BABYLON.Vector3(0.01, 0, tiltRoll);
        }
        // Think: Pondering user's question, looking up and away
        else if (currentGesture.name === "think" && activeBones.head) {
          const thinkPitch = -Math.sin(p * Math.PI) * 0.045;
          const thinkYaw = Math.sin(p * Math.PI) * 0.05;
          activeBones.head.rotation = new BABYLON.Vector3(thinkPitch, thinkYaw, 0.02);
          if (activeBones.rightArm) activeBones.rightArm.rotation = new BABYLON.Vector3(0, 0, 0.65);
        }
        // Shy: Flustered by compliment, looking down shyly
        else if (currentGesture.name === "shy") {
          const shyPitch = Math.sin(p * Math.PI) * 0.06;
          if (activeBones.head) activeBones.head.rotation = new BABYLON.Vector3(shyPitch, 0, 0);
          if (activeBones.leftArm) activeBones.leftArm.rotation = new BABYLON.Vector3(0, 0, -0.72);
          if (activeBones.rightArm) activeBones.rightArm.rotation = new BABYLON.Vector3(0, 0, 0.72);
        }
        // Excited: Joyful bounce, laughing and cheerful
        else if (currentGesture.name === "excited") {
          const bounce = Math.abs(Math.sin(p * 14.0)) * 0.022;
          if (activeBones.chest) activeBones.chest.rotation = new BABYLON.Vector3(-bounce * 0.6, 0, 0);
          if (activeBones.head) activeBones.head.rotation = new BABYLON.Vector3(bounce * 0.9, 0, 0);
        }
        // Shrug: Lifting shoulders playfully
        else if (currentGesture.name === "shrug") {
          const shrug = Math.sin(p * Math.PI) * 0.065;
          if (activeBones.head) activeBones.head.rotation = new BABYLON.Vector3(0, 0, shrug * 0.4);
          if (activeBones.leftArm) activeBones.leftArm.rotation = new BABYLON.Vector3(0, 0, -0.92 + shrug);
          if (activeBones.rightArm) activeBones.rightArm.rotation = new BABYLON.Vector3(0, 0, 0.92 - shrug);
        }
        // Lean: Leans forward attentively toward camera
        else if (currentGesture.name === "lean" && activeBones.spine) {
          const leanPitch = Math.sin(p * Math.PI) * 0.05;
          activeBones.spine.rotation = new BABYLON.Vector3(leanPitch, 0, 0);
        }

      } else {
        currentGesture.name = "none";
      }
    }

    // 5. Auto-Blink Controller (blinks every 2.5 - 4.5 seconds with smooth curve)
    if (animTime - lastBlink > nextBlink) {
      const elapsed = animTime - lastBlink - nextBlink;
      if (elapsed < blinkDuration) {
        const blinkWeight = Math.sin((elapsed / blinkDuration) * Math.PI);
        setMorphInfluence(["まばたき", "blink", "eye_blink", "eyeblink"], blinkWeight);
      } else {
        setMorphInfluence(["まばたき", "blink", "eye_blink", "eyeblink"], 0);
        lastBlink = animTime;
        nextBlink = 2.5 + Math.random() * 2.5; // Next blink in 2.5s - 5.0s
      }
    }
  });

  engine.runRenderLoop(() => {
    scene.render();
  });

  window.addEventListener("resize", () => {
    engine.resize();
  });
}

// --- 2. 3D Character Model Loader (GLB / DLP3D / PMX / Procedural) ---
async function loadCharacterModel(filename) {
  currentCharacterFile = filename;
  
  // Clean up any previously loaded meshes
  if (loadedGlbMeshes.length > 0) {
    loadedGlbMeshes.forEach(m => m.dispose());
    loadedGlbMeshes = [];
  }
  if (avatarMesh) {
    avatarMesh.dispose();
    avatarMesh = null;
  }
  activeMorphTargets = {};
  activeMorphTargetManager = null;

  if (filename === "procedural") {
    buildProceduralAvatar();
    camera.setTarget(new BABYLON.Vector3(0, 1.0, 0));
    camera.radius = 2.8;
    return;
  }

  // Load character (GLB or PMX)
  try {
    const lastSlash = filename.lastIndexOf("/");
    const rootUrl = lastSlash !== -1 ? "characters/" + filename.substring(0, lastSlash + 1) : "characters/";
    const sceneFilename = lastSlash !== -1 ? filename.substring(lastSlash + 1) : filename;

    const result = await BABYLON.SceneLoader.ImportMeshAsync("", rootUrl, sceneFilename, scene);
    loadedGlbMeshes = result.meshes;

    const rootMesh = result.meshes[0];

    // Compute bounding box across all loaded meshes to detect PMX vs GLB scale
    let min = new BABYLON.Vector3(Infinity, Infinity, Infinity);
    let max = new BABYLON.Vector3(-Infinity, -Infinity, -Infinity);

    for (const m of result.meshes) {
      if (m.getBoundingInfo && m.getTotalVertices && m.getTotalVertices() > 0) {
        const b = m.getBoundingInfo().boundingBox;
        min = BABYLON.Vector3.Minimize(min, b.minimumWorld);
        max = BABYLON.Vector3.Maximize(max, b.maximumWorld);
      }
    }

    const rawHeight = max.y - min.y;

    // Normalization: MMD PMX models are ~15-20 units tall compared to GLB 1.6m
    if (rawHeight > 3.0) {
      const standardHeight = 1.6;
      const scaleFactor = standardHeight / rawHeight;
      rootMesh.scaling = new BABYLON.Vector3(scaleFactor, scaleFactor, scaleFactor);
      rootMesh.position.y = -min.y * scaleFactor;
      console.log(`[Avatar] Scaled PMX model height from ${rawHeight.toFixed(2)} to ${standardHeight}m (scaleFactor: ${scaleFactor.toFixed(4)})`);
    } else {
      rootMesh.position = new BABYLON.Vector3(0, 0, 0);
    }

    // Adjust camera target directly to character head height (~1.35m)
    camera.setTarget(new BABYLON.Vector3(0, 1.35, 0));
    camera.radius = 2.4;

    // Relax horizontal T-Pose into natural standing pose
    relaxArmBones(result);

    // Autoplay embedded GLB animation groups (DLP3D avatars)
    if (result.animationGroups && result.animationGroups.length > 0) {
      currentAnimationGroups = result.animationGroups;
      currentAnimationGroups.forEach(ag => {
        ag.stop();
        ag.play(true);
      });
      console.log(`[Avatar] Started ${result.animationGroups.length} embedded animation tracks.`);
    } else {
      currentAnimationGroups = [];
    }

    // Scan all meshes for MorphTargetManager to drive visemes & emotions
    activeMorphTargets = {};
    for (const mesh of result.meshes) {
      if (mesh.morphTargetManager) {
        const mgr = mesh.morphTargetManager;
        const count = mgr.numTargets;
        for (let i = 0; i < count; i++) {
          const target = mgr.getTarget(i);
          const raw = target.name.trim();
          const lower = raw.toLowerCase();
          if (!activeMorphTargets[raw]) activeMorphTargets[raw] = [];
          activeMorphTargets[raw].push(target);
          if (!activeMorphTargets[lower]) activeMorphTargets[lower] = [];
          activeMorphTargets[lower].push(target);
        }
      }
    }

    console.log(`[Avatar] Loaded ${filename} with ${Object.keys(activeMorphTargets).length} blendshapes across meshes`);
    console.log("[Avatar] Available morph targets:", Object.keys(activeMorphTargets));
  } catch (err) {
    console.warn(`[Avatar] Could not load ${filename}, falling back to procedural avatar:`, err);
    buildProceduralAvatar();
  }
}

// Relax T-Pose arms down into a natural standing rest pose and map skeleton bones
function relaxArmBones(result) {
  activeBones = { spine: null, chest: null, neck: null, head: null, leftArm: null, rightArm: null };
  const skeletons = result.skeletons || [];
  for (const sk of skeletons) {
    for (const bone of sk.bones) {
      const name = bone.name;
      const lower = name.toLowerCase();

      // Japanese MMD names & standard bone names
      if (name === "左腕" || lower.includes("arm_l") || lower.includes("upperarm.l")) {
        activeBones.leftArm = bone;
        bone.rotate(BABYLON.Axis.Z, -0.92, BABYLON.Space.LOCAL);
      } else if (name === "右腕" || lower.includes("arm_r") || lower.includes("upperarm.r")) {
        activeBones.rightArm = bone;
        bone.rotate(BABYLON.Axis.Z, 0.92, BABYLON.Space.LOCAL);
      } else if (name === "左ひじ" || lower.includes("elbow_l") || lower.includes("forearm.l")) {
        bone.rotate(BABYLON.Axis.Y, 0.22, BABYLON.Space.LOCAL);
      } else if (name === "右ひじ" || lower.includes("elbow_r") || lower.includes("forearm.r")) {
        bone.rotate(BABYLON.Axis.Y, -0.22, BABYLON.Space.LOCAL);
      } else if (name === "上半身" || lower.includes("spine")) {
        activeBones.spine = bone;
      } else if (name === "上半身2" || lower.includes("chest")) {
        activeBones.chest = bone;
      } else if (name === "首" || lower.includes("neck")) {
        activeBones.neck = bone;
      } else if (name === "頭" || lower.includes("head")) {
        activeBones.head = bone;
      }
    }
  }
}


// Procedural anime avatar head fallback
function buildProceduralAvatar() {
  avatarMesh = BABYLON.MeshBuilder.CreateSphere("avatarHead", { diameter: 1.0, segments: 32 }, scene);
  avatarMesh.position.y = 1.0;

  const skinMat = new BABYLON.StandardMaterial("skinMat", scene);
  skinMat.diffuseColor = new BABYLON.Color3(1.0, 0.88, 0.82);
  skinMat.specularColor = new BABYLON.Color3(0.1, 0.1, 0.1);
  avatarMesh.material = skinMat;

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

  const mouthMat = new BABYLON.StandardMaterial("mouthMat", scene);
  mouthMat.diffuseColor = new BABYLON.Color3(0.85, 0.3, 0.4);

  const mouth = BABYLON.MeshBuilder.CreatePlane("mouth", { width: 0.16, height: 0.06 }, scene);
  mouth.position = new BABYLON.Vector3(0, 0.82, 0.49);
  mouth.material = mouthMat;
  mouth.parent = avatarMesh;

  const hairMat = new BABYLON.StandardMaterial("hairMat", scene);
  hairMat.diffuseColor = new BABYLON.Color3(0.9, 0.35, 0.6);
  const hair = BABYLON.MeshBuilder.CreateSphere("hair", { diameterX: 1.08, diameterY: 1.08, diameterZ: 1.05 }, scene);
  hair.position = new BABYLON.Vector3(0, 1.1, -0.05);
  hair.material = hairMat;
  hair.parent = avatarMesh;

  activeMorphTargets = { proceduralMouth: mouth };
}

// Universal Morph Target setter across all submeshes
function setMorphInfluence(names, value) {
  if (!Array.isArray(names)) names = [names];
  for (const name of names) {
    if (activeMorphTargets[name]) {
      for (const t of activeMorphTargets[name]) {
        t.influence = value;
      }
    }
    const lower = name.toLowerCase();
    for (const [k, targets] of Object.entries(activeMorphTargets)) {
      if (k.includes(lower) || k.includes(name)) {
        for (const t of targets) {
          t.influence = value;
        }
      }
    }
  }
}

// --- 3. Real-time Viseme Lip-Sync & Emotion Blendshapes ---
function applyVisemeFrame(frame) {
  const openness = frame.openness || 0;

  // 1. If using procedural avatar
  if (activeMorphTargets.proceduralMouth) {
    const scaleY = Math.max(0.3, openness * 3.2);
    const scaleX = 1.0 + (frame.visemes?.aa || 0) * 0.8;
    activeMorphTargets.proceduralMouth.scaling.y = scaleY;
    activeMorphTargets.proceduralMouth.scaling.x = scaleX;
    return;
  }

  // 2. If using GLB avatar: search for mouth / jaw / vowel targets
  setMorphInfluence(["mouthopen", "jawopen", "mouth_open", "viseme_aa"], openness);

  // 3. MMD Japanese Visemes (あ / い / う / え / お)
  setMorphInfluence(["あ", "a"], openness * (frame.visemes?.aa !== undefined ? frame.visemes.aa : 0.85));
  setMorphInfluence(["い", "i"], openness * (frame.visemes?.ih !== undefined ? frame.visemes.ih : 0.3));
  setMorphInfluence(["う", "u"], openness * (frame.visemes?.ou !== undefined ? frame.visemes.ou : 0.3));
}

function applyEmotionBlendshape(emotion, blendshapes) {
  // Update HUD badge
  const emoji = EMOTION_EMOJIS[emotion.toLowerCase()] || "🙂";
  emotionTag.querySelector(".emoji").textContent = emoji;
  emotionTag.querySelector(".label").textContent = emotion.toUpperCase();
  emotionTag.classList.remove("hidden");

  const cleanEmotion = emotion.toLowerCase();

  // Reset temporary expression morphs
  for (const [name, targets] of Object.entries(activeMorphTargets)) {
    if (name.includes("smile") || name.includes("blush") || name.includes("happy") || name === "笑い" || name === "照れ" || name === "にこり" || name === "困り") {
      if (Array.isArray(targets)) {
        for (const t of targets) t.influence = 0;
      } else if (targets.influence !== undefined) {
        targets.influence = 0;
      }
    }
  }

  // Drive GLB emotion blendshapes if available
  setMorphInfluence([cleanEmotion], 0.8);
  if (cleanEmotion === "happy") setMorphInfluence(["smile"], 0.8);

  // Drive MMD Japanese Emotion Morphs (Shiori Novella)
  if (cleanEmotion.includes("happy") || cleanEmotion.includes("smile")) {
    setMorphInfluence(["笑い", "にこり"], 0.8);
  } else if (cleanEmotion.includes("blush") || cleanEmotion.includes("shy") || cleanEmotion.includes("tsundere")) {
    setMorphInfluence(["照れ"], 0.9);
  } else if (cleanEmotion.includes("sad")) {
    setMorphInfluence(["困り"], 0.7);
  } else if (cleanEmotion.includes("wink")) {
    setMorphInfluence(["ウィンク"], 1.0);
  }
}

// --- 4. WebAudio Streaming Queue ---
function playNextAudioChunk() {
  if (audioQueue.length === 0) {
    isPlayingAudio = false;
    if (activeMorphTargets.proceduralMouth) {
      activeMorphTargets.proceduralMouth.scaling.y = 0.5;
      activeMorphTargets.proceduralMouth.scaling.x = 1.0;
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

// --- 5. WebSocket Streaming Connection ---
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
      if (data.gesture && data.gesture !== "none" && window.triggerGesture) {
        window.triggerGesture(data.gesture);
      }
      audioQueue.push(data);
      if (!isPlayingAudio) {
        playNextAudioChunk();
      }
    }
  };
}

// --- 6. Character, Model & Settings Operations ---
async function fetchCharacters() {
  try {
    charactersList.innerHTML = `<div class="loading-spinner">Loading characters...</div>`;
    const res = await fetch("/api/characters");
    const data = await res.json();

    charactersList.innerHTML = "";
    
    // Procedural fallback option
    const procCard = document.createElement("div");
    procCard.className = `model-card ${currentCharacterFile === "procedural" ? "active" : ""}`;
    procCard.innerHTML = `
      <div class="title">Anime Head (Procedural)</div>
      <div class="details"><span>Lightweight zero-download</span></div>
    `;
    procCard.onclick = () => selectCharacter("procedural");
    charactersList.appendChild(procCard);

    data.characters.forEach((c) => {
      const card = document.createElement("div");
      card.className = `model-card ${c.file === currentCharacterFile ? "active" : ""}`;
      card.innerHTML = `
        <div class="title">${c.name}</div>
        <div class="details">
          <span>${c.description}</span>
          <span>${c.size_mb} MB</span>
        </div>
      `;
      card.onclick = () => selectCharacter(c.file);
      charactersList.appendChild(card);
    });
  } catch (err) {
    charactersList.innerHTML = `<p class="desc" style="color: #ff5252;">Failed to load characters: ${err.message}</p>`;
  }
}

async function selectCharacter(charFile) {
  try {
    await fetch("/api/characters/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ character_file: charFile }),
    });
    await loadCharacterModel(charFile);
    fetchCharacters();
  } catch (err) {
    alert("Error changing character: " + err.message);
  }
}

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

// --- Voice Reference Audio Picker & Upload ---
const uploadVoiceBtn = document.getElementById("upload-voice-btn");
const voiceFileInput = document.getElementById("voice-file-input");

if (uploadVoiceBtn && voiceFileInput) {
  uploadVoiceBtn.onclick = () => voiceFileInput.click();
  voiceFileInput.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    voiceStatus.className = "status-msg";
    voiceStatus.textContent = `Uploading & converting ${file.name}...`;

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/voice/upload", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (res.ok && data.success) {
        voiceStatus.className = "status-msg success";
        voiceStatus.textContent = `✓ Active voice reference set to: ${data.filename}`;
        voicePathInput.value = data.path;
      } else {
        voiceStatus.className = "status-msg error";
        voiceStatus.textContent = `✗ ${data.detail || "Upload failed"}`;
      }
    } catch (err) {
      voiceStatus.className = "status-msg error";
      voiceStatus.textContent = `✗ Error: ${err.message}`;
    }
  };
}

async function applyVoice() {
  const path = voicePathInput.value.trim();
  if (!path) return;

  voiceStatus.className = "status-msg";
  voiceStatus.textContent = "Validating & converting voice file...";

  try {
    const res = await fetch("/api/voice/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ voice_path: path }),
    });
    const data = await res.json();
    if (res.ok && data.success) {
      voiceStatus.className = "status-msg success";
      const finalName = data.voice.active_wav_path ? data.voice.active_wav_path.split(/[\\/]/).pop() : data.voice.filename;
      voiceStatus.textContent = `✓ Active voice reference set to: ${finalName}`;
      if (data.voice.active_wav_path) {
        voicePathInput.value = data.voice.active_wav_path;
      }
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
    if (cfg.tts?.voice_name && voicePresetSelect) {
      voicePresetSelect.value = cfg.tts.voice_name;
    }
  } catch (e) {
    console.error("Config load error:", e);
  }
}

// --- 7. Event Listeners ---
if (voicePresetSelect) {
  voicePresetSelect.onchange = async () => {
    const selectedVoice = voicePresetSelect.value;
    try {
      await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: { tts: { voice_name: selectedVoice } } }),
      });
      voiceStatus.className = "status-msg success";
      voiceStatus.textContent = `✓ Neural voice preset set to: ${selectedVoice}`;
    } catch (err) {
      voiceStatus.className = "status-msg error";
      voiceStatus.textContent = `✗ Failed to update voice preset: ${err.message}`;
    }
  };
}

chatForm.onsubmit = (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

  subtitleText.textContent = "";
  subtitleBox.classList.remove("hidden");
  if (window.triggerGesture) {
    window.triggerGesture("think");
  }
  ws.send(JSON.stringify({ text: text }));
  chatInput.value = "";
};

openSettingsBtn.onclick = () => {
  settingsDrawer.classList.remove("hidden");
  fetchCharacters();
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

// --- Character Lore & Personality Auto-Generator ---
const autoCharNameInput = document.getElementById("auto-char-name-input");
const autoGenPromptBtn = document.getElementById("auto-gen-prompt-btn");
const genPromptStatus = document.getElementById("gen-prompt-status");

if (autoGenPromptBtn && autoCharNameInput) {
  autoGenPromptBtn.onclick = async () => {
    const charName = autoCharNameInput.value.trim();
    if (!charName) {
      alert("Please enter a character name first.");
      return;
    }

    genPromptStatus.className = "status-msg";
    genPromptStatus.textContent = `🔍 Searching internet for '${charName}' lore & synthesizing personality...`;
    autoGenPromptBtn.disabled = true;

    try {
      const res = await fetch("/api/character/generate_personality", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ character_name: charName }),
      });
      const data = await res.json();

      if (res.ok && data.success) {
        systemPromptInput.value = data.system_prompt;
        genPromptStatus.className = "status-msg success";
        genPromptStatus.textContent = `✓ Generated & saved personality for ${data.character_name}! (Source: ${data.matched_title || 'Web Lore'})`;
      } else {
        genPromptStatus.className = "status-msg error";
        genPromptStatus.textContent = `✗ ${data.detail || "Failed to generate personality."}`;
      }
    } catch (err) {
      genPromptStatus.className = "status-msg error";
      genPromptStatus.textContent = `✗ Error: ${err.message}`;
    } finally {
      autoGenPromptBtn.disabled = false;
    }
  };
}


// --- Custom Model Import & Drag-and-Drop ---
const uploadCharBtn = document.getElementById("upload-char-btn");
const charFileInput = document.getElementById("char-file-input");

if (uploadCharBtn && charFileInput) {
  uploadCharBtn.onclick = () => charFileInput.click();
  charFileInput.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    await uploadAndLoadCharacter(file);
  };
}

async function uploadAndLoadCharacter(file) {
  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await fetch("/api/characters/upload", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    if (res.ok && data.success) {
      await loadCharacterModel(data.filename);
      fetchCharacters();
    } else {
      alert("Failed to upload model: " + (data.detail || "Unknown error"));
    }
  } catch (err) {
    alert("Error uploading model: " + err.message);
  }
}

// Drag & drop support on 3D viewport
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", async (e) => {
  e.preventDefault();
  if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
    const file = e.dataTransfer.files[0];
    if (file.name.toLowerCase().endsWith(".glb") || file.name.toLowerCase().endsWith(".gltf")) {
      await uploadAndLoadCharacter(file);
    }
  }
});

// --- Start Application ---
window.addEventListener("DOMContentLoaded", () => {
  initBabylon();
  connectWebSocket();
  loadConfig();
});
