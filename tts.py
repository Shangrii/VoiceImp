# -*- coding: utf-8 -*-
"""Speech synthesis. Backends: piper (local), sapi (Windows), edge and tiktok (online).
Each function returns (pcm_int16_mono, sample_rate)."""

import json
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent


def _read_wav(path: str):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        data = w.readframes(w.getnframes())
    pcm = np.frombuffer(data, dtype=np.int16)
    if ch == 2:
        pcm = pcm.reshape(-1, 2).mean(axis=1).astype(np.int16)
    return pcm, sr


def list_piper_voices() -> list[str]:
    vdir = ROOT / "voices"
    return sorted(p.name for p in vdir.glob("*.onnx")) if vdir.exists() else []


def list_sapi_voices() -> list[str]:
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        v = win32com.client.Dispatch("SAPI.SpVoice")
        return [tok.GetDescription() for tok in v.GetVoices()]
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Piper (neural, local)
# --------------------------------------------------------------------------- #
def synth_piper(cfg: dict, text: str):
    piper_exe = (ROOT / cfg["piper_exe"]).resolve()
    voice_model = (ROOT / cfg["voice_model"]).resolve()
    vj = voice_model.with_suffix(voice_model.suffix + ".json")
    sr = json.loads(vj.read_text(encoding="utf-8"))["audio"]["sample_rate"]
    cmd = [
        str(piper_exe), "-m", str(voice_model), "--output-raw",
        "--length_scale", str(cfg.get("piper_length_scale", 1.0)),
        "--noise_scale", str(cfg.get("piper_noise_scale", 0.667)),
    ]
    proc = subprocess.run(
        cmd, input=text.encode("utf-8"),
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    return np.frombuffer(proc.stdout, dtype=np.int16), sr


# --------------------------------------------------------------------------- #
# SAPI5 (classic Windows voices)
# --------------------------------------------------------------------------- #
def synth_sapi(text: str, voice_desc: str = "", rate: int = 0):
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    if voice_desc:
        for tok in voice.GetVoices():
            if voice_desc.lower() in tok.GetDescription().lower():
                voice.Voice = tok
                break
    voice.Rate = int(rate)

    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    tmp = tempfile.mktemp(suffix=".wav")
    stream.Open(tmp, 3, False)            # SSFMCreateForWrite
    voice.AudioOutputStream = stream
    voice.Speak(text)
    stream.Close()
    try:
        pcm, sr = _read_wav(tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return pcm, sr


# --------------------------------------------------------------------------- #
# TikTok TTS (via public API)
# --------------------------------------------------------------------------- #
TIKTOK_ENDPOINTS = [
    "https://tiktok-tts.weilnet.workers.dev/api/generation",
    "https://gesserit.co/api/tiktok-tts",
]


def _tiktok_chunks(text: str, n: int = 290):
    words, out, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > n:
            out.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        out.append(cur)
    return out or [text.strip()[:n]]


def synth_tiktok(text: str, voice: str = "en_us_006"):
    import base64
    import io
    import requests
    import soundfile as sf

    pieces, sr = [], 24000
    for chunk in _tiktok_chunks(text):
        data = None
        for url in TIKTOK_ENDPOINTS:
            try:
                r = requests.post(url, json={"text": chunk, "voice": voice}, timeout=20)
                j = r.json()
                data = j.get("data") or j.get("base64")
                if data:
                    break
            except Exception:
                continue
        if not data:
            raise RuntimeError("TikTok TTS did not respond (no internet or invalid voice?).")
        raw = base64.b64decode(data)
        audio, sr = sf.read(io.BytesIO(raw), dtype="int16", always_2d=False)
        if audio.ndim > 1:
            audio = audio[:, 0]
        pieces.append(audio)
    return (np.concatenate(pieces) if pieces else np.zeros(0, np.int16)), sr


# --------------------------------------------------------------------------- #
# Edge TTS (Microsoft neural voices, free)
# --------------------------------------------------------------------------- #
def synth_edge(text: str, voice: str = "es-MX-JorgeNeural",
               pitch: str = "+0Hz", rate: str = "+0%"):
    import asyncio
    import io
    import edge_tts
    import soundfile as sf

    async def _gen():
        comm = edge_tts.Communicate(text, voice, pitch=pitch, rate=rate)
        buf = b""
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                buf += chunk["data"]
        return buf

    mp3 = asyncio.run(_gen())
    if not mp3:
        raise RuntimeError("Edge TTS returned no audio (no internet or invalid voice?).")
    audio, sr = sf.read(io.BytesIO(mp3), dtype="int16", always_2d=False)
    if audio.ndim > 1:
        audio = audio[:, 0]
    return audio, sr


# --------------------------------------------------------------------------- #
def synthesize(cfg: dict, text: str):
    backend = cfg.get("backend", "piper")
    if backend == "sapi":
        return synth_sapi(text, cfg.get("sapi_voice", ""), int(cfg.get("sapi_rate", 0)))
    if backend == "tiktok":
        return synth_tiktok(text, cfg.get("tiktok_voice", "en_us_006"))
    if backend == "edge":
        return synth_edge(text, cfg.get("edge_voice", "es-MX-JorgeNeural"),
                          cfg.get("edge_pitch", "+0Hz"), cfg.get("edge_rate", "+0%"))
    return synth_piper(cfg, text)


def validate(cfg: dict):
    backend = cfg.get("backend", "piper")
    if backend in ("tiktok", "edge"):
        return
    if backend == "sapi":
        if not list_sapi_voices():
            raise RuntimeError("No SAPI voices available.")
        return
    piper_exe = (ROOT / cfg["piper_exe"]).resolve()
    voice_model = (ROOT / cfg["voice_model"]).resolve()
    vj = voice_model.with_suffix(voice_model.suffix + ".json")
    if not piper_exe.exists():
        raise FileNotFoundError(f"piper.exe not found: {piper_exe}")
    if not voice_model.exists() or not vj.exists():
        raise FileNotFoundError(f"Piper voice not found: {voice_model}")
