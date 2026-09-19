import os
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DEST_DIR = Path(r"G:\Program\Ai Waifu\services\f5-tts\checkpoints")
DEST_DIR.mkdir(parents=True, exist_ok=True)
TARGET_FILE = DEST_DIR / "model_1250000.safetensors"
EXPECTED_SIZE = 1348435761
NUM_THREADS = 16

if TARGET_FILE.exists() and TARGET_FILE.stat().st_size == EXPECTED_SIZE:
    print(f"File already complete: {TARGET_FILE.stat().st_size} bytes")
    sys.exit(0)

url = "https://hf-mirror.com/SWivid/F5-TTS/resolve/main/F5TTS_v1_Base/model_1250000.safetensors"
print("Resolving final CDN URL...")
session = requests.Session()
res = session.head(url, allow_redirects=True, timeout=15)
cdn_url = res.url
total_length = int(res.headers.get("content-length", EXPECTED_SIZE))
print(f"Content-Length: {total_length} bytes ({total_length / 1024 / 1024:.2f} MB)")

chunk_size = (total_length + NUM_THREADS - 1) // NUM_THREADS
ranges = []
for i in range(NUM_THREADS):
    start = i * chunk_size
    end = min((i + 1) * chunk_size - 1, total_length - 1)
    if start <= end:
        ranges.append((i, start, end))

# Pre-allocate or open file for random-access write
with open(TARGET_FILE, "wb") as f:
    f.seek(total_length - 1)
    f.write(b"\0")

downloaded_bytes = 0
t0 = time.time()
lock_time = [time.time()]

def download_part(part_idx, start, end):
    global downloaded_bytes
    headers = {"Range": f"bytes={start}-{end}"}
    for attempt in range(5):
        try:
            with requests.get(cdn_url, headers=headers, stream=True, timeout=20) as r:
                r.raise_for_status()
                curr = start
                with open(TARGET_FILE, "r+b") as out_f:
                    out_f.seek(start)
                    for chunk in r.iter_content(chunk_size=128 * 1024):
                        if chunk:
                            out_f.write(chunk)
                            downloaded_bytes += len(chunk)
                            curr += len(chunk)
                            now = time.time()
                            if now - lock_time[0] > 1.0:
                                lock_time[0] = now
                                speed = (downloaded_bytes / (1024 * 1024)) / (now - t0)
                                pct = (downloaded_bytes / total_length) * 100
                                mb = downloaded_bytes / (1024 * 1024)
                                print(f"{pct:.1f}% ({mb:.1f} MB / {total_length/1024/1024:.1f} MB) - {speed:.2f} MB/s", flush=True)
            return True
        except Exception as e:
            time.sleep(1)
            continue
    raise RuntimeError(f"Part {part_idx} failed after 5 retries")

print(f"Starting {NUM_THREADS}-thread parallel download...")
with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
    futures = [executor.submit(download_part, idx, s, e) for idx, s, e in ranges]
    for fut in as_completed(futures):
        fut.result()

dur = time.time() - t0
print(f"Successfully downloaded in {dur:.1f}s! ({total_length / (1024 * 1024) / dur:.2f} MB/s)")
print(f"Final file size: {TARGET_FILE.stat().st_size} bytes")
