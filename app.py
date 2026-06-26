# -*- coding: utf-8 -*-
"""VoiceImp console version (no GUI). Uses the same engine as the GUI."""

import sys
import time

import engine as eng


def main():
    cfg = eng.load_config()

    def on_state(s):
        labels = {
            "listening": "Listening...", "recording": "Recording...",
            "transcribing": "Transcribing...", "speaking": "Speaking...",
            "idle": "Stopped.", "error": "ERROR",
        }
        print(f"  [{labels.get(s, s)}]")

    machine = eng.VoiceEngine(
        cfg,
        on_state=on_state,
        on_transcription=lambda t: print(f"\n  You said: {t}"),
        on_error=lambda e: print(f"  [!] {e}"),
        on_info=lambda m: print(f"  {m}"),
    )

    mode = "open mic (VAD)" if cfg.get("mode") == "openmic" else f"push-to-talk [{cfg.get('hotkey', 'f8').upper()}]"
    print("=" * 56)
    print("  VoiceImp (console)")
    print(f"  CUDA GPU: {'yes' if eng.cuda_available() else 'no (CPU)'}")
    print(f"  Mode    : {mode}")
    print("=" * 56)

    try:
        machine.start()
    except Exception as exc:
        print(f"\nCould not start: {exc}")
        sys.exit(1)

    print("  Running. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nExiting...")
        machine.stop()


if __name__ == "__main__":
    main()
