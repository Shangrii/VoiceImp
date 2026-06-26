# -*- coding: utf-8 -*-
"""VoiceImp graphical interface (customtkinter)."""

import os
import queue
import sys
import threading

# pythonw.exe (no console) leaves stdout/stderr as None and some libraries break.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import customtkinter as ctk

import catalog
import engine as eng
import hardware

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

STATE_UI = {
    "idle":         ("Stopped",            "#6b7280"),
    "loading":      ("Loading voice...",   "#f59e0b"),
    "listening":    ("Listening",          "#22c55e"),
    "recording":    ("Recording",          "#ef4444"),
    "transcribing": ("Transcribing",       "#f59e0b"),
    "speaking":     ("Speaking",           "#a855f7"),
    "error":        ("Error",              "#ef4444"),
}

DEFAULT_INPUT = "(System default)"
NONE_OPT = "None"


def unique_names(devs):
    seen, out = set(), []
    for d in devs:
        if d["name"] not in seen:
            seen.add(d["name"]); out.append(d["name"])
    return out


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("VoiceImp")
        self.geometry("560x720")
        self.minsize(520, 680)

        self.cfg = eng.load_config()
        self.events: "queue.Queue" = queue.Queue()
        self.engine = eng.VoiceEngine(
            self.cfg,
            on_state=lambda s: self.events.put(("state", s)),
            on_transcription=lambda t: self.events.put(("text", t)),
            on_error=lambda e: self.events.put(("error", e)),
            on_info=lambda m: self.events.put(("info", m)),
        )
        self.running = False
        self.inputs, self.outputs = eng.list_devices()
        self.voices = catalog.voice_presets()

        self._build_ui()
        self._poll()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 2))
        ctk.CTkLabel(head, text="VoiceImp", font=("Segoe UI", 24, "bold")).pack(side="left")
        ctk.CTkLabel(head, text="GPU ✓" if eng.cuda_available() else "CPU",
                     text_color="#9ca3af").pack(side="right", pady=8)

        self.status = ctk.CTkLabel(self, text="Stopped", font=("Segoe UI", 19, "bold"),
                                   fg_color="#1f2937", corner_radius=12, height=54)
        self.status.grid(row=1, column=0, sticky="ew", padx=18, pady=(6, 4))
        meter = ctk.CTkFrame(self, fg_color="transparent")
        meter.grid(row=2, column=0, sticky="ew", padx=18)
        meter.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(meter, text="Mic", width=34, anchor="w").grid(row=0, column=0)
        self.level = ctk.CTkProgressBar(meter, height=12)
        self.level.set(0); self.level.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.tabs = ctk.CTkTabview(self, fg_color=("#e5e7eb", "#171a20"))
        self.tabs.grid(row=3, column=0, sticky="nsew", padx=12, pady=(8, 4))
        for name in ("Voice", "Audio", "Advanced"):
            self.tabs.add(name)
        self._build_tab_voice(self.tabs.tab("Voice"))
        self._build_tab_audio(self.tabs.tab("Audio"))
        self._build_tab_advanced(self.tabs.tab("Advanced"))

        self.toggle = ctk.CTkButton(self, text="▶  Start", height=46,
                                    font=("Segoe UI", 16, "bold"), command=self._toggle)
        self.toggle.grid(row=4, column=0, sticky="ew", padx=18, pady=(6, 4))
        self.log = ctk.CTkTextbox(self, height=84)
        self.log.grid(row=5, column=0, sticky="ew", padx=18, pady=(2, 14))
        self._log("Ready. Pick a voice and press Start.")

        self._refresh_mode_rows()

    def _build_tab_voice(self, t):
        t.grid_columnconfigure(0, weight=1)

        self._label(t, "Category")
        self.cat_menu = ctk.CTkOptionMenu(
            t, values=catalog.categories(self.voices),
            command=self._on_category, dynamic_resizing=False)
        self.cat_menu.set(self._cur_cat()); self.cat_menu.pack(fill="x", padx=10)
        self._label(t, "Voice")
        self.voice_menu = ctk.CTkOptionMenu(
            t, values=[catalog.voice_label(p) for p in catalog.voices_in(self._cur_cat(), self.voices)],
            command=self._on_voice, dynamic_resizing=False)
        self.voice_menu.set(self._cur_voice_label()); self.voice_menu.pack(fill="x", padx=10)

        self._label(t, "Capture")
        self.mode_seg = ctk.CTkSegmentedButton(
            t, values=["Open mic", "Push-to-talk"], command=self._on_mode)
        self.mode_seg.set("Open mic" if self.cfg.get("mode") == "openmic" else "Push-to-talk")
        self.mode_seg.pack(fill="x", padx=10)

        self.ptt_row = ctk.CTkFrame(t, fg_color="transparent")
        ctk.CTkLabel(self.ptt_row, text="Key:").pack(side="left")
        self.hotkey_lbl = ctk.CTkLabel(self.ptt_row, text=self.cfg.get("hotkey", "f8").upper(),
                                       font=("Segoe UI", 14, "bold"))
        self.hotkey_lbl.pack(side="left", padx=8)
        ctk.CTkButton(self.ptt_row, text="Change", width=84,
                      command=self._change_hotkey).pack(side="left")

        self.vad_row = ctk.CTkFrame(t, fg_color="transparent")
        ctk.CTkLabel(self.vad_row, text="Microphone sensitivity").pack(anchor="w")
        self.sens = ctk.CTkSlider(self.vad_row, from_=0, to=100, command=self._on_sens)
        self.sens.set(self.cfg.get("vad_sensitivity", 60)); self.sens.pack(fill="x")

    def _build_tab_audio(self, t):
        t.grid_columnconfigure(0, weight=1)
        self._label(t, "Microphone (your voice)")
        self.in_menu = self._menu(t, self._input_values(), self._cur_input(), self._on_input)
        self._label(t, "Output → Game (CABLE Input)")
        self.out_menu = self._menu(t, unique_names(self.outputs), self._cur_output(), self._on_output)
        self._label(t, "Monitor (hear yourself)")
        self.mon_menu = self._menu(t, [NONE_OPT] + unique_names(self.outputs),
                                   self._cur_monitor(), self._on_monitor)

    def _build_tab_advanced(self, t):
        t.grid_columnconfigure(0, weight=1)
        self._label(t, "Performance (based on your hardware)")
        self.perf_menu = self._menu(t, [p["label"] for p in hardware.PRESETS.values()],
                                    self._cur_perf_label(), self._on_perf)
        ctk.CTkLabel(t, text="Larger models = more accuracy, more latency.",
                     justify="left", text_color="#9ca3af").pack(anchor="w", padx=10, pady=(8, 0))

        self._label(t, "Windows voices (SAPI)")
        ctk.CTkLabel(t, text="SAPI voices installed in Windows show up automatically in the\n"
                             "'Windows / SAPI' category. Restart the app after installing new ones.",
                     justify="left", text_color="#9ca3af").pack(anchor="w", padx=10)

    def _label(self, parent, text):
        ctk.CTkLabel(parent, text=text, anchor="w",
                     text_color="#9ca3af").pack(anchor="w", padx=10, pady=(12, 2))

    def _menu(self, parent, values, current, command):
        m = ctk.CTkOptionMenu(parent, values=values, command=command, dynamic_resizing=False)
        if current in values:
            m.set(current)
        m.pack(fill="x", padx=10)
        return m

    # ---- current state ---- #
    def _cur_voice(self):
        p = catalog.find_voice(self.cfg.get("voice_preset"), self.voices)
        if not p and self.voices:
            p = self.voices[0]
        return p

    def _cur_cat(self):
        p = self._cur_voice()
        if p:
            return p["cat"]
        cats = catalog.categories(self.voices)
        return cats[0] if cats else ""

    def _cur_voice_label(self):
        p = self._cur_voice()
        return catalog.voice_label(p) if p else ""

    def _cur_perf_label(self):
        key = hardware.current_key(self.cfg) or hardware.recommend()
        return hardware.PRESETS[key]["label"]

    def _input_values(self):
        return [DEFAULT_INPUT] + unique_names(self.inputs)

    def _match(self, cfg_val, names, fallback):
        if not cfg_val:
            return fallback
        for n in names:
            if str(cfg_val).lower() in n.lower():
                return n
        return fallback

    def _cur_input(self):
        return self._match(self.cfg.get("input_device"), unique_names(self.inputs), DEFAULT_INPUT)

    def _cur_output(self):
        names = unique_names(self.outputs)
        return self._match(self.cfg.get("output_device"), names, names[0] if names else "")

    def _cur_monitor(self):
        return self._match(self.cfg.get("monitor_device"), unique_names(self.outputs), NONE_OPT)

    def _refresh_mode_rows(self):
        self.ptt_row.pack_forget(); self.vad_row.pack_forget()
        if self.cfg.get("mode") == "openmic":
            self.vad_row.pack(fill="x", padx=10, pady=(6, 0), after=self.mode_seg)
        else:
            self.ptt_row.pack(fill="x", padx=10, pady=(6, 0), after=self.mode_seg)

    # ---- callbacks ---- #
    def _on_category(self, cat):
        vs = catalog.voices_in(cat, self.voices)
        labels = [catalog.voice_label(p) for p in vs]
        self.voice_menu.configure(values=labels)
        if labels:
            self.voice_menu.set(labels[0])
            self._on_voice(labels[0])

    def _on_voice(self, label):
        cat = self.cat_menu.get()
        for p in catalog.voices_in(cat, self.voices):
            if catalog.voice_label(p) == label:
                catalog.apply_voice(self.cfg, p)
                self._save()
                self._log(f"Voice: {label}")
                break

    def _on_mode(self, val):
        self.cfg["mode"] = "openmic" if val == "Open mic" else "ptt"
        self._save(); self._refresh_mode_rows()

    def _on_sens(self, val):
        self.cfg["vad_sensitivity"] = round(val); self._save()

    def _on_perf(self, label):
        key = hardware.LABEL_TO_KEY.get(label)
        if key:
            hardware.apply_preset(self.cfg, key)
            self.engine._model = None
            self._save(); self._restart_if_running()

    def _on_input(self, val):
        self.cfg["input_device"] = None if val == DEFAULT_INPUT else val
        self._save(); self._restart_if_running()

    def _on_output(self, val):
        self.cfg["output_device"] = val; self._save(); self._restart_if_running()

    def _on_monitor(self, val):
        self.cfg["monitor_device"] = None if val == NONE_OPT else val
        self._save(); self._restart_if_running()

    def _change_hotkey(self):
        self.hotkey_lbl.configure(text="press a key...")

        def grab():
            try:
                import keyboard
                ev = keyboard.read_event(suppress=False)
                while ev.event_type != "down":
                    ev = keyboard.read_event(suppress=False)
                self.events.put(("hotkey", ev.name))
            except Exception as exc:
                self.events.put(("error", f"Could not read the key: {exc}"))
        threading.Thread(target=grab, daemon=True).start()

    # ---- start / stop ---- #
    def _toggle(self):
        if self.running:
            self.engine.stop(); self.running = False
            self.toggle.configure(text="▶  Start")
        else:
            self.toggle.configure(text="Loading...", state="disabled")
            self._set_state("loading")

            def run():
                try:
                    self.engine.start()
                    self.running = True
                    self.events.put(("enable_toggle", True))
                except Exception as exc:
                    self.events.put(("error", str(exc)))
                    self.events.put(("state", "error"))
                    self.events.put(("enable_toggle", False))
            threading.Thread(target=run, daemon=True).start()

    def _restart_if_running(self):
        if not self.running:
            return

        def run():
            self.engine.stop()
            try:
                self.engine.start()
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=run, daemon=True).start()

    # ---- UI loop ---- #
    def _poll(self):
        self.level.set(min(1.0, self.engine.current_level / 0.15))
        while not self.events.empty():
            kind, val = self.events.get()
            if kind == "state":
                self._set_state(val)
            elif kind == "text":
                self._log(f"You: {val}")
            elif kind == "info":
                self._log(val)
            elif kind == "error":
                self._log(f"[!] {val}")
            elif kind == "hotkey":
                self.cfg["hotkey"] = val
                self.hotkey_lbl.configure(text=val.upper())
                self._save()
            elif kind == "enable_toggle":
                self.toggle.configure(state="normal",
                                      text="■  Stop" if val else "▶  Start")
        self.after(33, self._poll)

    def _set_state(self, state):
        text, color = STATE_UI.get(state, (state, "#1f2937"))
        self.status.configure(text=text, fg_color=color)

    def _log(self, msg):
        self.log.insert("end", msg + "\n"); self.log.see("end")

    def _save(self):
        eng.save_config(self.cfg)

    def _on_close(self):
        try:
            if self.running:
                self.engine.stop()
        finally:
            self.destroy()


if __name__ == "__main__":
    App().mainloop()
