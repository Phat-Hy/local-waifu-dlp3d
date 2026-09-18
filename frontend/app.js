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
let activeBones = { spine: null, chest: null, neck: null, head: null, leftArm: null, rightArm: null, leftEye: null, rightEye: null };
let currentAnimationGroups = [];
let currentCharacterFile = null;
let ws = null;
let audioQueue = [];
let isPlayingAudio = false;
let audioContext = null;
let audioAnalyser = null;
let audioFreqData = null;
let liveSpeechEnergy = 0.0;
let liveSpeechPitchCentroid = 20.0;
let lastSpeechEnergy = 0.0;
let speechCadenceBeat = 0.0;

let gazeState = {
  currentX: 0.0,
  currentY: 0.0,
  targetX: 0.0,
  targetY: 0.0,
  nextSaccadeTime: 1.8,
  lastSaccadeTime: 0.0,
};

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

  // --- Organic Kinematics, Acoustic Speech Coupling, Saccadic Gaze & Gesture State ---
  let animTime = 0;
  let lastBlink = 0;
  let nextBlink = 3.2;
  const blinkDuration = 0.22;

  let currentGesture = {
    name: "none",
    startTime: 0,
    duration: 1.5
  };

  // Multi-harmonic non-periodic fractal noise function for biological human motion
  function organicHarmonic(t, speed, seed) {
    return Math.sin(t * speed + seed) * 0.55
         + Math.sin(t * (speed * 1.732) + seed * 1.41) * 0.3
         + Math.sin(t * (speed * 3.141) + seed * 2.23) * 0.15;
  }

  window.triggerGesture = function(gestureName) {
    if (!gestureName || gestureName === "none") return;
    console.log(`[Avatar] Conversation Gesture Triggered: ${gestureName}`);
    currentGesture = {
      name: gestureName.toLowerCase().trim(),
      startTime: animTime,
      duration: gestureName === "wave" ? 2.6 : (gestureName === "excited" ? 2.0 : 1.8)
    };
  };

  scene.onBeforeRenderObservable.add(() => {
    const dt = engine.getDeltaTime() / 1000.0;
    animTime += dt;

    // --- Layer A: Live Acoustic Audio Analysis (WebAudio 60 FPS FFT) ---
    if (isPlayingAudio && audioAnalyser && audioFreqData) {
      audioAnalyser.getByteFrequencyData(audioFreqData);
      let sum = 0;
      let weightedSum = 0;
      for (let i = 0; i < audioFreqData.length; i++) {
        const val = audioFreqData[i];
        sum += val;
        weightedSum += val * (i + 1);
      }
      const avg = sum / audioFreqData.length;
      const targetEnergy = Math.min(1.0, (avg / 128.0) * 1.85);

      // Fast attack, smooth decay
      const attackSpeed = targetEnergy > liveSpeechEnergy ? 0.42 : 0.22;
      liveSpeechEnergy += (targetEnergy - liveSpeechEnergy) * attackSpeed;

      // Detect syllable transients
      const energyDelta = targetEnergy - lastSpeechEnergy;
      if (energyDelta > 0.11) {
        speechCadenceBeat = Math.min(1.0, speechCadenceBeat + energyDelta * 1.6);
      }
      lastSpeechEnergy = targetEnergy;
      speechCadenceBeat *= 0.88;

      // Pitch / Spectral centroid
      const centroid = sum > 15 ? (weightedSum / sum) : 20.0;
      liveSpeechPitchCentroid += (centroid - liveSpeechPitchCentroid) * 0.2;
    } else {
      liveSpeechEnergy += (0 - liveSpeechEnergy) * 0.15;
      speechCadenceBeat *= 0.85;
      liveSpeechPitchCentroid += (20.0 - liveSpeechPitchCentroid) * 0.15;
    }

    // --- Layer B: Saccadic Gaze & Human Eye Wandering ---
    if (animTime - gazeState.lastSaccadeTime > gazeState.nextSaccadeTime) {
      gazeState.lastSaccadeTime = animTime;
      gazeState.nextSaccadeTime = 1.1 + Math.random() * 2.2;

      // Natural gaze aversion when formulating thoughts or speaking
      if (currentGesture.name === "think" || (isPlayingAudio && Math.random() < 0.28)) {
        gazeState.targetX = (Math.random() > 0.5 ? 0.05 : -0.05) + (Math.random() - 0.5) * 0.02;
        gazeState.targetY = -0.035 - Math.random() * 0.035;
      } else {
        // Direct eye contact with micro-saccades between left eye, right eye & mouth
        gazeState.targetX = (Math.random() - 0.5) * 0.026;
        gazeState.targetY = (Math.random() - 0.5) * 0.02;
      }
    }
    gazeState.currentX += (gazeState.targetX - gazeState.currentX) * 0.22;
    gazeState.currentY += (gazeState.targetY - gazeState.currentY) * 0.22;

    if (activeBones.leftEye) {
      activeBones.leftEye.rotation = new BABYLON.Vector3(gazeState.currentY * 0.8, gazeState.currentX * 0.8, 0);
    }
    if (activeBones.rightEye) {
      activeBones.rightEye.rotation = new BABYLON.Vector3(gazeState.currentY * 0.8, gazeState.currentX * 0.8, 0);
    }

    // --- Layer 1: Organic Multi-Octave Breathing & Torso Sway (Fractal Kinematics) ---
    if (activeBones.chest || activeBones.spine) {
      const breathDepth = 0.012 + organicHarmonic(animTime, 0.28, 2.1) * 0.005;
      const breathFreq = isPlayingAudio ? 2.1 : 1.55;
      const breathPitch = Math.sin(animTime * breathFreq) * breathDepth;

      const swayLateral = organicHarmonic(animTime, 0.48, 1.3) * 0.009;
      const swayYaw = organicHarmonic(animTime, 0.32, 4.7) * 0.006;
      const chestVocalLift = -liveSpeechEnergy * 0.018 - speechCadenceBeat * 0.012;

      const bone = activeBones.chest || activeBones.spine;
      bone.rotation = new BABYLON.Vector3(breathPitch + chestVocalLift, swayYaw, swayLateral);
    }

    // --- Layer 2: Acoustic Speech Head Dynamics (Syllables, Pitch & Gaze) ---
    if (activeBones.head) {
      const syllableNod = (Math.sin(animTime * 6.2) * liveSpeechEnergy * 0.032) + (speechCadenceBeat * 0.025);
      const pitchLift = liveSpeechPitchCentroid > 24 ? -(liveSpeechPitchCentroid - 24) * 0.0012 : 0;
      const speechTilt = Math.sin(animTime * 2.3) * liveSpeechEnergy * 0.022;

      const idleHeadPitch = organicHarmonic(animTime, 0.72, 0.8) * 0.012;
      const idleHeadYaw = organicHarmonic(animTime, 0.54, 3.2) * 0.014;
      const idleHeadRoll = organicHarmonic(animTime, 0.61, 5.1) * 0.01;

      activeBones.head.rotation = new BABYLON.Vector3(
        idleHeadPitch + syllableNod + pitchLift + gazeState.currentY * 0.6,
        idleHeadYaw + gazeState.currentX * 0.7,
        idleHeadRoll + speechTilt
      );
    }

    // --- Layer 3: Dynamic Co-Speech Hand & Arm Phrasing ---
    const armSpeechEnergy = liveSpeechEnergy * 0.16;
    const armBreathSway = Math.sin(animTime * 1.55) * 0.012;

    if (activeBones.leftArm && (!currentGesture || currentGesture.name === "none" || currentGesture.name === "wave" || currentGesture.name === "nod" || currentGesture.name === "tilt")) {
      activeBones.leftArm.rotation = new BABYLON.Vector3(
        liveSpeechEnergy * 0.05,
        0,
        -0.92 + armBreathSway + armSpeechEnergy
      );
    }
    if (activeBones.rightArm && (!currentGesture || currentGesture.name === "none" || currentGesture.name === "nod" || currentGesture.name === "tilt")) {
      activeBones.rightArm.rotation = new BABYLON.Vector3(
        liveSpeechEnergy * 0.05,
        0,
        0.92 - armBreathSway - armSpeechEnergy
      );
    }

    // --- Layer 4: Contextual Conversational Gestures ---
    if (currentGesture.name !== "none") {
      const gElapsed = animTime - currentGesture.startTime;
      const gDuration = currentGesture.duration;

      if (gElapsed < gDuration) {
        const rawP = gElapsed / gDuration;
        const p = rawP * rawP * (3.0 - 2.0 * rawP); // Cubic Hermite smoothstep

        if (currentGesture.name === "wave" && activeBones.rightArm) {
          const armHeight = -0.38 - Math.sin(p * Math.PI) * 0.82;
          const handWave = Math.sin(p * 22.0) * 0.3;
          activeBones.rightArm.rotation = new BABYLON.Vector3(0, handWave, armHeight);
          if (activeBones.head) {
            activeBones.head.rotation.x += -0.02;
            activeBones.head.rotation.y += -0.04;
            activeBones.head.rotation.z += 0.03;
          }
        } else if (currentGesture.name === "nod" && activeBones.head) {
          const nodPitch = Math.sin(p * 14.0) * 0.065 * (1.0 - p * 0.4);
          activeBones.head.rotation.x += nodPitch;
          if (activeBones.chest) activeBones.chest.rotation.x += nodPitch * 0.4;
        } else if (currentGesture.name === "tilt" && activeBones.head) {
          const tiltRoll = Math.sin(p * Math.PI) * 0.11;
          activeBones.head.rotation.z += tiltRoll;
        } else if (currentGesture.name === "think" && activeBones.head) {
          const thinkPitch = -Math.sin(p * Math.PI) * 0.055;
          const thinkYaw = Math.sin(p * Math.PI) * 0.065;
          activeBones.head.rotation.x += thinkPitch;
          activeBones.head.rotation.y += thinkYaw;
          if (activeBones.rightArm) activeBones.rightArm.rotation = new BABYLON.Vector3(0, 0, 0.65);
        } else if (currentGesture.name === "shy") {
          const shyPitch = Math.sin(p * Math.PI) * 0.07;
          if (activeBones.head) activeBones.head.rotation.x += shyPitch;
          if (activeBones.leftArm) activeBones.leftArm.rotation = new BABYLON.Vector3(0, 0, -0.72);
          if (activeBones.rightArm) activeBones.rightArm.rotation = new BABYLON.Vector3(0, 0, 0.72);
        } else if (currentGesture.name === "excited") {
          const bounce = Math.abs(Math.sin(p * 15.0)) * 0.026;
          if (activeBones.chest) activeBones.chest.rotation.x += -bounce * 0.7;
          if (activeBones.head) activeBones.head.rotation.x += bounce * 1.0;
        } else if (currentGesture.name === "shrug") {
          const shrug = Math.sin(p * Math.PI) * 0.075;
          if (activeBones.head) activeBones.head.rotation.z += shrug * 0.4;
          if (activeBones.leftArm) activeBones.leftArm.rotation = new BABYLON.Vector3(0, 0, -0.92 + shrug);
          if (activeBones.rightArm) activeBones.rightArm.rotation = new BABYLON.Vector3(0, 0, 0.92 - shrug);
        } else if (currentGesture.name === "lean" && activeBones.spine) {
          const leanPitch = Math.sin(p * Math.PI) * 0.06;
          activeBones.spine.rotation.x += leanPitch;
        }
      } else {
        currentGesture.name = "none";
      }
    }

    // --- Layer 5: Natural Human Blink Controller (Asymmetric Curve & Speech Punctuation) ---
    if (animTime - lastBlink > nextBlink) {
      const elapsed = animTime - lastBlink - nextBlink;
      if (elapsed < blinkDuration) {
        // Fast close (first 35% of duration), slightly slower open (remaining 65%)
        const t = elapsed / blinkDuration;
        const blinkWeight = t < 0.35 
          ? Math.sin((t / 0.35) * (Math.PI / 2))
          : Math.cos(((t - 0.35) / 0.65) * (Math.PI / 2));
        setMorphInfluence(["まばたき", "blink", "eye_blink", "eyeblink"], blinkWeight);
      } else {
        setMorphInfluence(["まばたき", "blink", "eye_blink", "eyeblink"], 0);
        lastBlink = animTime;
        // Blinks occur every 2.4s to 4.8s
        nextBlink = 2.4 + Math.random() * 2.4;
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
      } else if (name === "左目" || lower.includes("eye_l") || lower.includes("eye.l")) {
        activeBones.leftEye = bone;
      } else if (name === "右目" || lower.includes("eye_r") || lower.includes("eye.r")) {
        activeBones.rightEye = bone;
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

  if (!audioAnalyser) {
    audioAnalyser = audioContext.createAnalyser();
    audioAnalyser.fftSize = 256;
    audioAnalyser.smoothingTimeConstant = 0.6;
    audioFreqData = new Uint8Array(audioAnalyser.frequencyBinCount);
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
    source.connect(audioAnalyser);
    audioAnalyser.connect(audioContext.destination);

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
