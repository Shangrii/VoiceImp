# -*- coding: utf-8 -*-
"""List audio devices to help configure config.json."""

import sounddevice as sd

print("INDEX | INPUT | OUTPUT | NAME")
print("-" * 70)
for idx, dev in enumerate(sd.query_devices()):
    mark_in = "MIC" if dev["max_input_channels"] > 0 else "   "
    mark_out = "OUT" if dev["max_output_channels"] > 0 else "   "
    print(f"  {idx:>3}  |  {mark_in}  |  {mark_out}  | {dev['name']}")

print("-" * 70)
print("Set 'output_device' to the name of 'CABLE Input' (the virtual mic your game reads).")
