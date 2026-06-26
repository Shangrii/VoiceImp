# -*- coding: utf-8 -*-
"""Voice engine: captures the mic, transcribes with faster-whisper and plays a
synthetic voice into a virtual microphone (CABLE Input) that any game or app reads."""

import json
import os
import sys
import sysconfig
import threading
import queue
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd

import tts

ROOT = Path(__file__).resolve().parent
SAMPLE_RATE_IN = 16000
LANG_VOICES = {"es": "es_MX-claude-high.onnx", "en": "en_US-amy-medium.onnx"}
BLOCK = 1024


def setup_cuda_dll_paths() -> list[str]:
    """Add the venv's CUDA DLLs to PATH before importing ctranslate2."""
    nvidia = Path(sysconfig.get_paths()["purelib"]) / "nvidia"
    bins = [str(p) for p in nvidia.glob("*/bin")] if nvidia.exists() else []
    if bins:
        os.environ["PATH"] = os.pathsep.join(bins) + os.pathsep + os.environ.get("PATH", "")
        for b in bins:
            try:
                os.add_dll_directory(b)
            except (OSError, AttributeError):
                pass
    return bins


setup_cuda_dll_paths()
import ctranslate2  # noqa: E402


def cuda_available() -> bool:
    try:
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Audio devices
# --------------------------------------------------------------------------- #
def _hostapi(substr: str):
    try:
        for i, a in enumerate(sd.query_hostapis()):
            if substr in a["name"].upper():
                return i
    except Exception:
        pass
    return None


def list_devices():
    """Real devices (WASAPI only), without the MME/DirectSound duplicates."""
    wasapi = _hostapi("WASAPI")
    inputs, outputs = [], []
    si, so = set(), set()
    for idx, dev in enumerate(sd.query_devices()):
        if wasapi is not None and dev["hostapi"] != wasapi:
            continue
        name = dev["name"]
        if dev["max_input_channels"] > 0 and name not in si:
            si.add(name); inputs.append({"index": idx, "name": name})
        if dev["max_output_channels"] > 0 and name not in so:
            so.add(name); outputs.append({"index": idx, "name": name})
    if not inputs and not outputs:
        for idx, dev in enumerate(sd.query_devices()):
            name = dev["name"]
            if dev["max_input_channels"] > 0 and name not in si:
                si.add(name); inputs.append({"index": idx, "name": name})
            if dev["max_output_channels"] > 0 and name not in so:
                so.add(name); outputs.append({"index": idx, "name": name})
    return inputs, outputs


def resolve_device(value, kind: str):
    """None | int | name -> device index. Prefers MME for output."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    want_input = kind == "input"
    target = str(value).lower().strip()
    mme = _hostapi("MME")
    matches = []
    for idx, dev in enumerate(sd.query_devices()):
        chans = dev["max_input_channels"] if want_input else dev["max_output_channels"]
        if chans <= 0:
            continue
        name = dev["name"].lower().strip()
        if target in name or (len(name) >= 10 and name in target):
            matches.append((idx, dev["hostapi"]))
    if not matches:
        return None
    for idx, ha in matches:
        if mme is not None and ha == mme:
            return idx
    return matches[0][0]


def list_voices() -> list[str]:
    vdir = ROOT / "voices"
    return sorted(p.name for p in vdir.glob("*.onnx")) if vdir.exists() else []


CONFIG = ROOT / "config.json"
CONFIG_DEFAULT = ROOT / "config.default.json"


def load_config() -> dict:
    path = CONFIG if CONFIG.exists() else CONFIG_DEFAULT
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(cfg: dict):
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Whisper hallucination filter (phrases it invents over silence/noise)
# --------------------------------------------------------------------------- #
HALLUCINATION_PATTERNS = (
    "subtitulos", "subtítulos", "amara.org", "subtitulado por",
    "gracias por ver", "gracias por su atencion", "gracias por su atención",
    "no olvides suscribirte", "suscribete", "suscríbete", "dale like",
    "subscribe", "thanks for watching", "thank you for watching",
    "www.", ".com", "♪", "[música]", "(música)", "[music]",
)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def is_hallucination(text: str) -> bool:
    t = _normalize(text)
    alnum = "".join(c for c in t if c.isalnum())
    if len(alnum) < 2:
        return True
    for p in HALLUCINATION_PATTERNS:
        if p in t:
            return True
    words = t.split()
    if len(words) >= 4 and len(set(words)) == 1:
        return True
    return False


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
class VoiceEngine:
    """States via on_state: idle | listening | recording | transcribing | speaking | error"""

    def __init__(self, cfg: dict,
                 on_state=None, on_transcription=None, on_error=None, on_info=None):
        self.cfg = cfg
        self.on_state = on_state or (lambda s: None)
        self.on_transcription = on_transcription or (lambda t: None)
        self.on_error = on_error or (lambda e: None)
        self.on_info = on_info or (lambda m: None)

        self.current_level = 0.0
        self.peak = 0.0

        self._running = threading.Event()
        self._speaking = threading.Event()
        self._lifecycle = threading.Lock()
        self._audio_q: "queue.Queue" = queue.Queue()
        self._proc_q: "queue.Queue" = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._stream = None
        self._model = None

        self.input_dev = None
        self.output_dev = None
        self.monitor_dev = None
        self.voice_sr = 22050

    def load_model(self):
        from faster_whisper import WhisperModel

        want_gpu = self.cfg.get("use_gpu", True) and cuda_available()
        device = "cuda" if want_gpu else "cpu"
        compute = self.cfg.get("whisper_compute_type", "auto")
        if compute == "auto":
            compute = "float16" if device == "cuda" else "int8"
        model_name = self.cfg.get("whisper_model", "small")
        local = ROOT / "models" / f"faster-whisper-{model_name}"
        model_id = str(local) if (local / "model.bin").exists() else model_name

        self.on_info(f"Loading Whisper '{model_name}' on {device.upper()} ({compute})...")
        try:
            self._model = WhisperModel(model_id, device=device, compute_type=compute)
        except Exception as exc:
            self.on_info(f"Failed on {device} ({exc}); falling back to CPU/int8.")
            self._model = WhisperModel(model_id, device="cpu", compute_type="int8")
            device = "cpu"
        warm = np.zeros(SAMPLE_RATE_IN, dtype=np.float32)
        list(self._model.transcribe(warm, language=self.cfg.get("language", "es"))[0])
        self.on_info(f"Whisper ready on {device.upper()}.")
        return device

    def _prepare(self):
        tts.validate(self.cfg)
        self.input_dev = resolve_device(self.cfg.get("input_device"), "input")
        self.output_dev = resolve_device(self.cfg.get("output_device"), "output")
        self.monitor_dev = resolve_device(self.cfg.get("monitor_device"), "output")
        if self.cfg.get("output_device") and self.output_dev is None:
            self.on_info(f"[warning] Could not find '{self.cfg['output_device']}' "
                         "(is VB-CABLE installed?). Playing through monitor/default.")

    def start(self):
        with self._lifecycle:
            if self._running.is_set():
                return
            self._prepare()
            for q in (self._audio_q, self._proc_q):
                try:
                    while True:
                        q.get_nowait()
                except queue.Empty:
                    pass
            if self._model is None:
                self.load_model()
            self._running.set()
            self._speaking.clear()

            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE_IN, channels=1, dtype="float32",
                blocksize=BLOCK, device=self.input_dev, callback=self._audio_cb,
            )
            self._stream.start()

            self._threads = [
                threading.Thread(target=self._capture_loop, daemon=True),
                threading.Thread(target=self._process_loop, daemon=True),
            ]
            for t in self._threads:
                t.start()
        self.on_state("listening")

    def stop(self):
        with self._lifecycle:
            self._running.clear()
            if self._stream is not None:
                try:
                    self._stream.stop(); self._stream.close()
                except Exception:
                    pass
                self._stream = None
            self._audio_q.put(None)
            self._proc_q.put(None)
            for t in self._threads:
                t.join(timeout=2)
            self._threads = []
            self.current_level = 0.0
        self.on_state("idle")

    # ---- capture ---- #
    def _audio_cb(self, indata, frames, time_info, status):
        rms = float(np.sqrt(np.mean(indata[:, 0] ** 2)) + 1e-9)
        self.current_level = rms
        self._audio_q.put((indata[:, 0].copy(), rms))

    def _capture_loop(self):
        sr = SAMPLE_RATE_IN
        preroll_n = max(1, int(self.cfg.get("vad_preroll", 0.25) * sr / BLOCK))
        hang_n = max(1, int(self.cfg.get("vad_silence", 0.6) * sr / BLOCK))
        start_n = 2
        max_n = int(15 * sr / BLOCK)
        min_samples = int(self.cfg.get("min_seconds", 0.4) * sr)
        min_voiced = max(1, int(self.cfg.get("min_voiced_ms", 250) / 1000 * sr / BLOCK))

        prebuf = deque(maxlen=preroll_n)
        in_speech = False
        voiced = 0
        silence = 0
        voiced_in_utt = 0
        utter: list[np.ndarray] = []
        was_held = False

        ema = 0.0
        noise = -1.0

        while self._running.is_set():
            item = self._audio_q.get()
            if item is None:
                break
            frame, rms = item
            mode = self.cfg.get("mode", "ptt")

            if self._speaking.is_set():
                in_speech = False; voiced = silence = voiced_in_utt = 0
                utter = []; prebuf.clear()
                continue

            if mode == "ptt":
                try:
                    import keyboard
                    held = keyboard.is_pressed(self.cfg.get("hotkey", "f8"))
                except Exception:
                    held = False
                if held:
                    if not was_held:
                        self.on_state("recording")
                    utter.append(frame)
                elif was_held:
                    self._flush(utter, min_samples)
                    utter = []
                    self.on_state("listening")
                was_held = held
                continue

            # open mic: adaptive VAD (threshold relative to ambient noise)
            ema = 0.85 * ema + 0.15 * rms
            if noise < 0:
                noise = rms
            sens = float(self.cfg.get("vad_sensitivity", 55))
            factor = 6.0 - (sens / 100.0) * 4.4
            abs_floor = 0.0015 + (1 - sens / 100.0) * 0.010
            threshold = max(abs_floor, noise * factor)
            speech = ema > threshold

            if not in_speech:
                noise = 0.97 * noise + 0.03 * rms
                prebuf.append(frame)
                if speech:
                    voiced += 1
                    if voiced >= start_n:
                        in_speech = True
                        utter = list(prebuf); prebuf.clear()
                        silence = 0
                        voiced_in_utt = voiced
                        self.on_state("recording")
                else:
                    voiced = 0
            else:
                utter.append(frame)
                if speech:
                    silence = 0
                    voiced_in_utt += 1
                else:
                    silence += 1
                if silence >= hang_n or len(utter) >= max_n:
                    in_speech = False
                    if voiced_in_utt >= min_voiced:
                        self._flush(utter, min_samples)
                    utter = []; voiced = silence = voiced_in_utt = 0
                    self.on_state("listening")

    def _flush(self, frames: list[np.ndarray], min_samples: int):
        if not frames:
            return
        audio = np.concatenate(frames).astype(np.float32)
        if audio.size < min_samples:
            return
        # only the most recent utterance matters: drop the stale ones
        try:
            while True:
                self._proc_q.get_nowait()
        except queue.Empty:
            pass
        self._proc_q.put(audio)

    # ---- transcription + synthesis + playback ---- #
    def _process_loop(self):
        while self._running.is_set():
            audio = self._proc_q.get()
            if audio is None:
                break
            try:
                self._process(audio)
            except Exception as exc:
                self.on_error(str(exc))
            finally:
                self._speaking.clear()
                try:
                    while True:
                        self._audio_q.get_nowait()
                except queue.Empty:
                    pass
                if self._running.is_set():
                    self.on_state("listening")

    def _process(self, audio):
        if self._model is None:
            self.load_model()
        plang = self.cfg.get("lang", "auto")
        self.on_state("transcribing")
        segs, info = self._model.transcribe(
            audio, language=(None if plang == "auto" else plang),
            beam_size=1,
            temperature=0.0,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
            compression_ratio_threshold=2.4,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300, speech_pad_ms=120),
        )
        parts = []
        for s in segs:
            if getattr(s, "no_speech_prob", 0.0) > 0.6:
                continue
            if getattr(s, "avg_logprob", 0.0) < -1.0:
                continue
            parts.append(s.text)
        text = "".join(parts).strip()
        if not text or is_hallucination(text):
            return
        self.on_transcription(text)

        out_lang = plang if plang != "auto" else (info.language if info.language in LANG_VOICES else "en")
        synth_cfg = self.cfg
        if plang == "auto":
            vmap = self.cfg.get("voice_map") or {}
            voice = vmap.get(out_lang) or LANG_VOICES.get(out_lang, LANG_VOICES["en"])
            synth_cfg = {**self.cfg, "voice_model": f"voices/{voice}"}

        self._speaking.set()
        self.on_state("speaking")
        pcm, sr = tts.synthesize(synth_cfg, text)
        self._play(pcm, sr)

    def _play(self, pcm: np.ndarray, sr: int):
        if pcm.size == 0:
            return
        targets = [d for d in (self.output_dev, self.monitor_dev) if d is not None] or [None]

        def _one(device):
            try:
                with sd.OutputStream(samplerate=sr, device=device,
                                     channels=1, dtype="int16") as s:
                    s.write(pcm)
            except Exception as exc:
                self.on_error(f"Audio output: {exc}")

        threads = [threading.Thread(target=_one, args=(d,), daemon=True) for d in targets]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
