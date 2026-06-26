# -*- coding: utf-8 -*-
"""Performance presets: each one sets the Whisper model and whether it uses the GPU."""

import subprocess

import engine

PRESETS = {
    "ultralight": {"label": "Ultralight (slow CPU)", "whisper_model": "base",     "use_gpu": False},
    "light":      {"label": "Light (CPU)",           "whisper_model": "small",    "use_gpu": False},
    "balanced":   {"label": "Balanced (mid GPU)",    "whisper_model": "small",    "use_gpu": True},
    "high":       {"label": "High (good GPU)",       "whisper_model": "medium",   "use_gpu": True},
    "maximum":    {"label": "Maximum (powerful GPU)","whisper_model": "large-v3", "use_gpu": True},
}

LABEL_TO_KEY = {v["label"]: k for k, v in PRESETS.items()}


def gpu_vram_mb():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return int(out.stdout.strip().splitlines()[0])
    except Exception:
        return None


def recommend() -> str:
    if not engine.cuda_available():
        return "light"
    vram = gpu_vram_mb() or 0
    if vram >= 10000:
        return "high"
    if vram >= 5000:
        return "balanced"
    return "light"


def current_key(cfg: dict):
    for key, p in PRESETS.items():
        if p["whisper_model"] == cfg.get("whisper_model") and \
           bool(p["use_gpu"]) == bool(cfg.get("use_gpu", True)):
            return key
    return None


def apply_preset(cfg: dict, key: str):
    p = PRESETS.get(key)
    if not p:
        return
    cfg["whisper_model"] = p["whisper_model"]
    cfg["use_gpu"] = p["use_gpu"]
