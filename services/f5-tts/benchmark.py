import time
import torch
import soundfile as sf
from pathlib import Path
from f5_tts.api import F5TTS

print("PyTorch CUDA available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("Device:", torch.cuda.get_device_name(0))

ckpt = r"G:\Program\Ai Waifu\services\f5-tts\checkpoints\model_1250000.safetensors"
ref_wav = r"G:\Program\Ai Waifu\voices\shiori_prompt_12s.wav"
ref_text = "Oh hey glad you're here. Come in and take a seat."
gen_text = "Hello! It is so lovely to meet you. I am ready to talk whenever you are!"

t0 = time.time()
print("Loading F5TTS model...")
f5 = F5TTS(model="F5TTS_v1_Base", ckpt_file=ckpt, ode_method="euler", device="cuda")
print(f"Model loaded in {time.time() - t0:.2f}s!")

# Warmup run
print("\n--- Warmup Run (nfe=16) ---")
t1 = time.time()
wav, sr, _ = f5.infer(
    ref_file=ref_wav,
    ref_text=ref_text,
    gen_text=gen_text,
    nfe_step=16,
    cfg_strength=2.0
)
inf_time = time.time() - t1
dur = len(wav) / sr
print(f"Warmup inference done in {inf_time:.2f}s for {dur:.2f}s audio (RTF: {inf_time / dur:.2f})!")

# Benchmark run 2 (pure inference, no torch CUDA init overhead)
print("\n--- Benchmark Run 2 (nfe=16) ---")
t2 = time.time()
wav2, sr2, _ = f5.infer(
    ref_file=ref_wav,
    ref_text=ref_text,
    gen_text="Master, welcome back! I was hoping you would talk to me today.",
    nfe_step=16,
    cfg_strength=2.0
)
inf_time2 = time.time() - t2
dur2 = len(wav2) / sr2
print(f"Benchmark run 2 done in {inf_time2:.2f}s for {dur2:.2f}s audio (RTF: {inf_time2 / dur2:.2f})!")

out_path = r"G:\Program\Ai Waifu\voices\shiori_f5_benchmark.wav"
sf.write(out_path, wav2, sr2)
print(f"Saved generated voice to {out_path} ({Path(out_path).stat().st_size} bytes)")
