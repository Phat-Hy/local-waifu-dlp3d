"""
GGUF Model and Audio Reference Scanner
Discovers local LLM models (.gguf) and voice reference files (.wav)
Extracts GGUF metadata (architecture, context length, quant type) without loading weights.
"""

import os
import struct
from pathlib import Path
from typing import Dict, Any, List, Optional


GGUF_MAGIC = b"GGUF"

# GGUF Value Types
GGUF_TYPE_UINT8 = 0
GGUF_TYPE_INT8 = 1
GGUF_TYPE_UINT16 = 2
GGUF_TYPE_INT16 = 3
GGUF_TYPE_UINT32 = 4
GGUF_TYPE_INT32 = 5
GGUF_TYPE_FLOAT32 = 6
GGUF_TYPE_BOOL = 7
GGUF_TYPE_STRING = 8
GGUF_TYPE_ARRAY = 9
GGUF_TYPE_UINT64 = 10
GGUF_TYPE_INT64 = 11
GGUF_TYPE_FLOAT64 = 12


def read_gguf_string(f) -> str:
    length_bytes = f.read(8)
    if len(length_bytes) < 8:
        return ""
    length = struct.unpack("<Q", length_bytes)[0]
    if length > 100000:  # safety check
        return ""
    str_bytes = f.read(length)
    return str_bytes.decode("utf-8", errors="replace")


def read_gguf_value(f, vtype: int) -> Any:
    if vtype == GGUF_TYPE_UINT8:
        return struct.unpack("<B", f.read(1))[0]
    elif vtype == GGUF_TYPE_INT8:
        return struct.unpack("<b", f.read(1))[0]
    elif vtype == GGUF_TYPE_UINT16:
        return struct.unpack("<H", f.read(2))[0]
    elif vtype == GGUF_TYPE_INT16:
        return struct.unpack("<h", f.read(2))[0]
    elif vtype == GGUF_TYPE_UINT32:
        return struct.unpack("<I", f.read(4))[0]
    elif vtype == GGUF_TYPE_INT32:
        return struct.unpack("<i", f.read(4))[0]
    elif vtype == GGUF_TYPE_FLOAT32:
        return struct.unpack("<f", f.read(4))[0]
    elif vtype == GGUF_TYPE_BOOL:
        return bool(struct.unpack("<B", f.read(1))[0])
    elif vtype == GGUF_TYPE_STRING:
        return read_gguf_string(f)
    elif vtype == GGUF_TYPE_UINT64:
        return struct.unpack("<Q", f.read(8))[0]
    elif vtype == GGUF_TYPE_INT64:
        return struct.unpack("<q", f.read(8))[0]
    elif vtype == GGUF_TYPE_FLOAT64:
        return struct.unpack("<d", f.read(8))[0]
    elif vtype == GGUF_TYPE_ARRAY:
        elem_type_bytes = f.read(4)
        if len(elem_type_bytes) < 4:
            return []
        elem_type = struct.unpack("<I", elem_type_bytes)[0]
        len_bytes = f.read(8)
        if len(len_bytes) < 8:
            return []
        arr_len = struct.unpack("<Q", len_bytes)[0]
        items = []
        for _ in range(min(arr_len, 20)):  # capped to avoid deep parsing
            items.append(read_gguf_value(f, elem_type))
        # Skip remaining if truncated
        if arr_len > 20:
            # We don't need full arrays of tokenizers for metadata inspection
            pass
        return items
    return None


def parse_gguf_metadata(file_path: str, max_keys: int = 150) -> Dict[str, Any]:
    """
    Parses GGUF header and metadata key-value pairs without loading model tensors.
    """
    metadata: Dict[str, Any] = {
        "valid": False,
        "path": file_path,
        "filename": os.path.basename(file_path),
        "size_bytes": 0,
        "size_formatted": "0 MB",
    }
    
    try:
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            metadata["error"] = "File not found"
            return metadata

        file_size = p.stat().st_size
        metadata["size_bytes"] = file_size
        if file_size >= 1024 * 1024 * 1024:
            metadata["size_formatted"] = f"{file_size / (1024**3):.2f} GB"
        else:
            metadata["size_formatted"] = f"{file_size / (1024**2):.1f} MB"

        with open(file_path, "rb") as f:
            magic = f.read(4)
            if magic != GGUF_MAGIC:
                metadata["error"] = f"Invalid magic header: {magic!r}, expected {GGUF_MAGIC!r}"
                return metadata

            version_bytes = f.read(4)
            if len(version_bytes) < 4:
                metadata["error"] = "Truncated header"
                return metadata
            version = struct.unpack("<I", version_bytes)[0]
            metadata["gguf_version"] = version

            tensor_count = struct.unpack("<Q", f.read(8))[0]
            kv_count = struct.unpack("<Q", f.read(8))[0]
            metadata["tensor_count"] = tensor_count
            metadata["kv_count"] = kv_count

            kv_pairs: Dict[str, Any] = {}
            for _ in range(min(kv_count, max_keys)):
                key = read_gguf_string(f)
                if not key:
                    break
                vtype_bytes = f.read(4)
                if len(vtype_bytes) < 4:
                    break
                vtype = struct.unpack("<I", vtype_bytes)[0]
                val = read_gguf_value(f, vtype)
                kv_pairs[key] = val

            metadata["metadata"] = kv_pairs
            metadata["valid"] = True

            # Extract user-friendly summary fields
            arch = kv_pairs.get("general.architecture", "unknown")
            metadata["architecture"] = arch
            metadata["name"] = kv_pairs.get("general.name", p.stem)
            metadata["context_length"] = kv_pairs.get(f"{arch}.context_length", kv_pairs.get("llama.context_length", 2048))
            metadata["block_count"] = kv_pairs.get(f"{arch}.block_count", 0)
            metadata["file_type"] = kv_pairs.get("general.file_type", None)
            metadata["quantization"] = kv_pairs.get("general.quantization_version", None)

    except Exception as e:
        metadata["error"] = str(e)

    return metadata


def scan_directory_for_models(directories: List[str], max_depth: int = 4) -> List[Dict[str, Any]]:
    """
    Recursively scans provided directories for .gguf model files.
    """
    found_models: List[Dict[str, Any]] = []
    seen_paths = set()

    for dir_path in directories:
        if not os.path.isdir(dir_path):
            continue

        for root, dirs, files in os.walk(dir_path):
            # Check depth relative to start dir
            rel_depth = len(Path(root).relative_to(Path(dir_path)).parts)
            if rel_depth > max_depth:
                dirs.clear()
                continue

            for file in files:
                if file.lower().endswith(".gguf"):
                    full_path = os.path.normpath(os.path.join(root, file))
                    if full_path not in seen_paths:
                        seen_paths.add(full_path)
                        meta = parse_gguf_metadata(full_path)
                        found_models.append(meta)

    return found_models


def validate_audio_file(file_path: str) -> Dict[str, Any]:
    """
    Validates a user-chosen voice reference audio file (.wav, .mp3, .flac, .ogg).
    """
    p = Path(file_path)
    res = {
        "valid": False,
        "path": file_path,
        "filename": p.name,
        "exists": p.exists(),
        "size_bytes": 0,
        "format": p.suffix.lower().lstrip("."),
    }
    if not p.exists() or not p.is_file():
        res["error"] = "File does not exist"
        return res

    res["size_bytes"] = p.stat().st_size
    supported = ["wav", "mp3", "flac", "ogg", "m4a"]
    if res["format"] not in supported:
        res["error"] = f"Unsupported audio format .{res['format']}. Supported: .wav, .flac, .mp3, .ogg"
        return res

    res["valid"] = True
    return res


def convert_audio_to_wav(source_path: str, destination_folder: str = "voices") -> str:
    """
    Converts .flac, .mp3, .ogg or existing .wav to clean 16-bit PCM WAV in the destination folder.
    """
    p = Path(source_path)
    dest_dir = Path(destination_folder)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_wav = dest_dir / f"{p.stem}.wav"

    try:
        import soundfile as sf
        data, samplerate = sf.read(str(p))
        sf.write(str(out_wav), data, samplerate, format="WAV", subtype="PCM_16")
        return str(out_wav)
    except Exception as e:
        print(f"[AudioConverter] Warning during soundfile conversion: {e}")
        if p.suffix.lower() == ".wav":
            import shutil
            shutil.copy2(p, out_wav)
            return str(out_wav)
        raise

