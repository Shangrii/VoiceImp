# -*- mode: python ; coding: utf-8 -*-
# Compilar:  .venv\Scripts\pyinstaller.exe VoiceImp.spec --noconfirm
from PyInstaller.utils.hooks import collect_all

CONSOLE = False

datas = []
binaries = []
hiddenimports = ["win32com", "win32com.client", "pythoncom", "win32timezone",
                 "soundfile", "sounddevice", "keyboard",
                 "engine", "tts", "catalog", "hardware"]

for pkg in ("faster_whisper", "ctranslate2", "edge_tts"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

datas += [
    ("voices_catalog.json", "."),
    ("config.default.json", "."),
    ("voices", "voices"),
    ("piper", "piper"),
    ("models", "models"),
]

a = Analysis(
    ["gui.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "torchaudio", "transformers", "faiss", "torchcrepe",
              "tkinter.test", "lib2to3", "pydoc_data"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="VoiceImp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=CONSOLE,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="voiceimp.ico",
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, upx_exclude=[],
    name="VoiceImp",
)
