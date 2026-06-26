# VoiceImp

For fun project made to mess with people online:
Speak into your microphone and have **your game of preference** hear a **synthetic voice** instead of your own. The app transcribes what you say (faster-whisper) and plays it back in a
different voice through a virtual microphone (**VB-CABLE**) that your game uses as input.

```
[Real microphone] --> VoiceImp --> "CABLE Input" (virtual mic) --> Game
                         |
                         |-- faster-whisper (STT, GPU or CPU)
                         '-- Piper / Windows SAPI / Edge / TikTok (TTS)
```


## Features

- **Open mic** (adaptive voice detection) or **Push-to-talk**.
- **Voice catalog** by category: local (Piper), Windows (SAPI), Microsoft (Edge) and
  TikTok — in Mexican Spanish and US English.
- **GPU (CUDA)** optional for Whisper; falls back to CPU if there is no GPU.
- Performance presets based on your hardware.

## Requirements

- Windows 10/11 (64-bit).
- **VB-CABLE**: https://vb-audio.com/Cable/
- Optional NVIDIA GPU (faster transcription; otherwise it uses the CPU).
- Only to run from source: Python 3.10+ (tested on 3.14).

## Installation

### Users (recommended)

Download **`VoiceImp_Setup.exe`** from the *Releases* section, run it and follow the
wizard. You don't need Python or any setup. It creates a desktop shortcut and ships
with the speech model bundled in (works offline).

Only one extra step is required: install **VB-CABLE** (the virtual microphone). The
installer opens its page and reminds you.

### From source (developers)

```bat
run.bat
```

`run.bat` creates the virtual environment, installs the dependencies and opens the
app. You need `piper/piper/piper.exe` and at least one `.onnx` voice in `voices/`
(see *Voices*).

To build the installer: `pyinstaller VoiceImp.spec --noconfirm`, then compile
`VoiceImp.iss` with Inno Setup.

## Set up VB-CABLE and Games

1. Install **VB-CABLE** (run as administrator → *Install Driver* → reboot).
2. In VoiceImp, **Audio** tab: output = **CABLE Input**, microphone = yours.
3. In Game → *Settings → Audio*: **Microphone Device = CABLE Output**, Voice mode.

## Usage

1. Open the app (`run.bat` or `VoiceImp.bat`).
2. Pick a **Category** and **Voice**, and the capture mode.
3. Press **Start** and talk.

Voices switch on the fly. Changing the device or the performance preset restarts the
engine.

## Voices

- **Piper (local)**: download `.onnx` + `.onnx.json` from
  https://rhasspy.github.io/piper-samples/ and drop them into `voices/`.
- **SAPI (Windows)**: detected automatically. Install more from *Settings → Time &
  language → Speech*.
- **Edge and TikTok**: online, no key required.

## Project layout

```
gui.py          UI (customtkinter)
engine.py       Capture, VAD/PTT, STT, playback
tts.py          Synthesis: Piper, SAPI, Edge, TikTok
catalog.py      Voice catalog
hardware.py     Performance presets
app.py          Console version
config.json     Settings (edited from the app)
voices_catalog.json
voices/         Piper models (.onnx)
piper/          piper.exe and DLLs
```

## About latency

The voice→text→voice flow waits until you finish talking before transcribing, so
there is a delay (silence + STT + synthesis). It is not a real-time voice changer.

## License

MIT — see `LICENSE`.
