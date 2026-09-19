import struct
import math
import os

def euler_to_quaternion(pitch, yaw, roll):
    # pitch (X), yaw (Y), roll (Z) in radians
    # MMD bone rotation order
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)

    w = cr * cp * cy + sr * sp * sy
    x = sr * cp * cy - cr * sp * sy
    y = cr * sp * cy + sr * cp * sy
    z = cr * cp * sy - sr * sp * cy
    return (x, y, z, w)

# Standard Japanese bone names in Shift-JIS
BONE_NAMES = {
    'head': '頭'.encode('shift_jis'),
    'neck': '首'.encode('shift_jis'),
    'spine': '上半身'.encode('shift_jis'),
    'chest': '上半身2'.encode('shift_jis'),
    'waist': '下半身'.encode('shift_jis'),
    'left_arm': '左腕'.encode('shift_jis'),
    'left_elbow': '左ひじ'.encode('shift_jis'),
    'left_wrist': '左手首'.encode('shift_jis'),
    'right_arm': '右腕'.encode('shift_jis'),
    'right_elbow': '右ひじ'.encode('shift_jis'),
    'right_wrist': '右手首'.encode('shift_jis'),
}

def write_vmd(filename, bone_frames, morph_frames=[]):
    with open(filename, 'wb') as f:
        # Header (30 bytes)
        magic = b'Vocaloid Motion Data 0002\x00\x00\x00\x00\x00'
        f.write(magic)
        # Model Name (20 bytes)
        model_name = 'WaifuMotion'.encode('shift_jis').ljust(20, b'\x00')
        f.write(model_name)
        # Bone frames count (4 bytes)
        f.write(struct.pack('<I', len(bone_frames)))
        # Bone frames
        default_interp = bytes([20, 20, 107, 107] * 16)
        for bf in bone_frames:
            # bone_name (15 bytes)
            name_bytes = bf['name'].ljust(15, b'\x00')[:15]
            frame_num = int(bf['frame'])
            px, py, pz = bf.get('pos', (0.0, 0.0, 0.0))
            qx, qy, qz, qw = bf.get('rot', (0.0, 0.0, 0.0, 1.0))
            interp = bf.get('interp', default_interp)
            f.write(name_bytes)
            f.write(struct.pack('<I', frame_num))
            f.write(struct.pack('<fff', px, py, pz))
            f.write(struct.pack('<ffff', qx, qy, qz, qw))
            f.write(interp)

        # Morph frames count (4 bytes)
        f.write(struct.pack('<I', len(morph_frames)))
        for mf in morph_frames:
            name_bytes = mf['name'].ljust(15, b'\x00')[:15]
            f.write(name_bytes)
            f.write(struct.pack('<I', int(mf['frame'])))
            f.write(struct.pack('<f', float(mf['weight'])))

        # Camera, Light, Shadow, IK (4 x 0)
        f.write(struct.pack('<IIII', 0, 0, 0, 0))

os.makedirs('frontend/motions', exist_ok=True)

# 1. Nod (Affirmative gentle double-nod, ~1.5s / 45 frames)
nod_frames = []
for frame in range(0, 50, 3):
    t = frame / 45.0
    if t <= 1.0:
        # Double nod curve
        pitch = math.sin(t * math.pi * 2.0) * math.sin(t * math.pi) * 0.28
    else:
        pitch = 0.0
    rot = euler_to_quaternion(pitch, 0.0, 0.0)
    nod_frames.append({'name': BONE_NAMES['head'], 'frame': frame, 'rot': rot})
write_vmd('frontend/motions/nod.vmd', nod_frames)
print('Generated nod.vmd')

# 2. Bow (Polite Japanese greeting bow, ~2.5s / 75 frames)
bow_frames = []
for frame in range(0, 80, 4):
    t = min(1.0, frame / 75.0)
    # Bow curve: goes down smoothly, holds slightly at bottom, rises smoothly
    if t < 0.4:
        # Bowing down
        depth = math.sin((t / 0.4) * (math.pi / 2))
    elif t < 0.6:
        # Holding bow
        depth = 1.0
    else:
        # Returning
        depth = math.cos(((t - 0.6) / 0.4) * (math.pi / 2))
    
    # Waist/spine pitches forward
    spine_rot = euler_to_quaternion(depth * 0.35, 0.0, 0.0)
    head_rot = euler_to_quaternion(depth * 0.20, 0.0, 0.0)
    bow_frames.append({'name': BONE_NAMES['spine'], 'frame': frame, 'rot': spine_rot})
    bow_frames.append({'name': BONE_NAMES['head'], 'frame': frame, 'rot': head_rot})
write_vmd('frontend/motions/bow.vmd', bow_frames)
print('Generated bow.vmd')

# 3. Thinking (Hand to chin, head tilted, ~3.0s / 90 frames)
think_frames = []
for frame in range(0, 95, 4):
    t = min(1.0, frame / 90.0)
    # Smooth in and out
    weight = math.sin(t * math.pi)
    head_rot = euler_to_quaternion(-weight * 0.08, weight * 0.12, -weight * 0.15)
    r_arm_rot = euler_to_quaternion(weight * 0.4, 0.0, -weight * 0.5)
    r_elbow_rot = euler_to_quaternion(0.0, 0.0, -weight * 1.6)
    
    think_frames.append({'name': BONE_NAMES['head'], 'frame': frame, 'rot': head_rot})
    think_frames.append({'name': BONE_NAMES['right_arm'], 'frame': frame, 'rot': r_arm_rot})
    think_frames.append({'name': BONE_NAMES['right_elbow'], 'frame': frame, 'rot': r_elbow_rot})
write_vmd('frontend/motions/thinking.vmd', think_frames)
print('Generated thinking.vmd')

# 4. Cheerful Speaking / Talk Gesture (~4.0s / 120 frames, seamlessly loopable)
talk_frames = []
for frame in range(0, 125, 3):
    t = (frame % 120) / 120.0
    phase = t * math.pi * 2.0
    
    # Conversational head nod & subtle tilt
    head_pitch = math.sin(phase * 2.0) * 0.06 + math.cos(phase * 3.0) * 0.03
    head_yaw = math.sin(phase) * 0.08
    head_roll = math.cos(phase * 1.5) * 0.04
    head_rot = euler_to_quaternion(head_pitch, head_yaw, head_roll)
    
    # Conversational chest breathing & weight shift
    chest_rot = euler_to_quaternion(math.sin(phase * 2.0) * 0.03, math.sin(phase) * 0.04, 0.0)
    
    # Expressive right hand gestures
    r_elbow_bend = -(0.8 + math.sin(phase * 2.0) * 0.35)
    r_arm_rot = euler_to_quaternion(math.sin(phase * 2.0) * 0.15, 0.0, -(0.35 + math.cos(phase) * 0.12))
    r_elbow_rot = euler_to_quaternion(0.0, 0.0, r_elbow_bend)
    
    # Subtle left hand balance gesture
    l_elbow_bend = (0.4 + math.cos(phase * 1.5) * 0.15)
    l_elbow_rot = euler_to_quaternion(0.0, 0.0, l_elbow_bend)

    talk_frames.append({'name': BONE_NAMES['head'], 'frame': frame, 'rot': head_rot})
    talk_frames.append({'name': BONE_NAMES['chest'], 'frame': frame, 'rot': chest_rot})
    talk_frames.append({'name': BONE_NAMES['right_arm'], 'frame': frame, 'rot': r_arm_rot})
    talk_frames.append({'name': BONE_NAMES['right_elbow'], 'frame': frame, 'rot': r_elbow_rot})
    talk_frames.append({'name': BONE_NAMES['left_elbow'], 'frame': frame, 'rot': l_elbow_rot})
write_vmd('frontend/motions/talk.vmd', talk_frames)
print('Generated talk.vmd')

# 5. Cheer / Joy celebration (~2.0s / 60 frames)
cheer_frames = []
for frame in range(0, 65, 3):
    t = min(1.0, frame / 60.0)
    weight = math.sin(t * math.pi)
    # Both hands raised joyfully
    r_arm_rot = euler_to_quaternion(0.0, 0.0, -weight * 1.3)
    l_arm_rot = euler_to_quaternion(0.0, 0.0, weight * 1.3)
    r_elbow_rot = euler_to_quaternion(0.0, 0.0, -weight * 1.1)
    l_elbow_rot = euler_to_quaternion(0.0, 0.0, weight * 1.1)
    head_rot = euler_to_quaternion(-weight * 0.18, 0.0, 0.0) # head tilted up happily

    cheer_frames.append({'name': BONE_NAMES['head'], 'frame': frame, 'rot': head_rot})
    cheer_frames.append({'name': BONE_NAMES['right_arm'], 'frame': frame, 'rot': r_arm_rot})
    cheer_frames.append({'name': BONE_NAMES['left_arm'], 'frame': frame, 'rot': l_arm_rot})
    cheer_frames.append({'name': BONE_NAMES['right_elbow'], 'frame': frame, 'rot': r_elbow_rot})
    cheer_frames.append({'name': BONE_NAMES['left_elbow'], 'frame': frame, 'rot': l_elbow_rot})
write_vmd('frontend/motions/cheer.vmd', cheer_frames)
print('Generated cheer.vmd')
