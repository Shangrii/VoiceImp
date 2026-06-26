# -*- coding: utf-8 -*-
"""Voice catalog, grouped by category (source and language)."""

import json
from pathlib import Path

import tts

ROOT = Path(__file__).resolve().parent
VOICES_FILE = ROOT / "voices_catalog.json"


def _load(p):
    return json.loads(p.read_text(encoding="utf-8"))


CAT_ORDER = ["Local · Auto", "Local · Spanish MX", "Local · English US",
             "Windows / SAPI",
             "Microsoft · Spanish MX", "Microsoft · English US",
             "TikTok · Spanish", "TikTok · English", "TikTok · Characters", "TikTok · Singing"]

_TK_CHARS = {"en_us_ghostface", "en_us_chewbacca", "en_us_c3po", "en_us_stitch",
             "en_us_stormtrooper", "en_us_rocket", "en_female_madam_leota",
             "en_male_ghosthost", "en_male_pirate",
             "en_male_jarvis", "en_male_santa", "en_male_grinch", "en_male_wizard",
             "en_female_grandma", "en_female_betty", "en_female_richgirl",
             "en_male_trevor", "en_male_deadpool", "en_male_m2_xhxs_m03_silly"}


def _category(e: dict) -> str:
    g = e["group"]
    if g == "Local":
        lang = e.get("lang")
        if lang == "es":
            return "Local · Spanish MX"
        if lang == "en":
            return "Local · English US"
        return "Local · Auto"
    if g == "SAPI":
        return "Windows / SAPI"
    if g == "Microsoft":
        return "Microsoft · Spanish MX" if e.get("lang") == "es" else "Microsoft · English US"
    if g == "TikTok":
        if e.get("lang") == "es":
            return "TikTok · Spanish"
        v = e.get("voice", "")
        if v in _TK_CHARS:
            return "TikTok · Characters"
        if "sing" in v or "f08" in v or "m03" in v or "ht_f08" in v:
            return "TikTok · Singing"
        return "TikTok · English"
    return g


def sapi_voices() -> list[dict]:
    """SAPI5 voices installed in Windows (including Loquendo if installed)."""
    out = []
    for desc in tts.list_sapi_voices():
        low = desc.lower()
        lang = "en" if ("english" in low or "(united states)" in low) else "es"
        label = desc.split(" - ")[0].replace("Microsoft ", "").replace(" Desktop", "").strip()
        out.append({"id": f"sapi::{desc}", "group": "SAPI", "label": label or desc,
                    "backend": "sapi", "lang": lang, "voice": desc})
    return out


def voice_presets() -> list[dict]:
    piper = set(tts.list_piper_voices())
    out = []
    for e in _load(VOICES_FILE):
        if e["backend"] == "piper":
            if e.get("lang") == "auto":
                if any(v not in piper for v in (e.get("voices") or {}).values()):
                    continue
            elif e.get("voice") not in piper:
                continue
        e["cat"] = _category(e)
        out.append(e)
    for e in sapi_voices():
        e["cat"] = _category(e)
        out.append(e)
    return out


def categories(presets=None):
    cats = {p["cat"] for p in (presets or voice_presets())}
    return [c for c in CAT_ORDER if c in cats] + sorted(cats - set(CAT_ORDER))


def voices_in(cat, presets=None):
    return [p for p in (presets or voice_presets()) if p["cat"] == cat]


def voice_label(p: dict) -> str:
    return p["label"]


def find_voice(pid, presets=None):
    for e in (presets or voice_presets()):
        if e["id"] == pid:
            return e
    return None


def apply_voice(cfg: dict, p: dict):
    b = p["backend"]
    cfg["backend"] = b
    cfg["lang"] = p.get("lang", "es")
    cfg["voice_map"] = p.get("voices") or {}
    if b == "piper":
        v = p.get("voice") or (p.get("voices") or {}).get("es") or ""
        if v:
            cfg["voice_model"] = f"voices/{v}"
    elif b == "edge":
        cfg["edge_voice"] = p["voice"]
        cfg["edge_pitch"] = p.get("edge_pitch", "+0Hz")
        cfg["edge_rate"] = p.get("edge_rate", "+0%")
    elif b == "tiktok":
        cfg["tiktok_voice"] = p["voice"]
    cfg["voice_preset"] = p["id"]
