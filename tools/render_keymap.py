#!/usr/bin/env python3
"""Render the Unix60 keymap layers as SVG keyboard diagrams.

Reads the same sources tools/validate_shield.py already parses and trusts
(unix60-layouts.dtsi for geometry, unix60.keymap for bindings), so the images
stay in sync with the actual shield files rather than being hand-drawn.

Run from the repo root:  python3 tools/render_keymap.py
Writes boards/shields/unix60/images/{base,fn}-layer.svg.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate_shield as vs  # noqa: E402

OUT_DIR = os.path.join(vs.REPO, vs.SHIELD, "images")

# 1 layout unit (100 in the .dtsi) -> this many SVG pixels.
SCALE = 0.5
GAP = 3  # px shaved off each side of a keycap, so adjacent keys show a seam.

# ZMK keycode (the part after "&kp ") -> short keycap label.
KP_LABELS = {
    "ESC": "Esc", "GRAVE": "`", "MINUS": "-", "EQUAL": "=", "BSLH": "\\",
    "TAB": "Tab", "LBKT": "[", "RBKT": "]", "BSPC": "Backspace",
    "LCTRL": "Ctrl", "SEMI": ";", "SQT": "'", "RET": "Enter",
    "LSHFT": "Shift", "RSHFT": "Shift", "COMMA": ",", "DOT": ".", "FSLH": "/",
    "LALT": "Alt", "LGUI": "Gui", "RGUI": "Gui", "RALT": "Alt",
    "SPACE": "", "N0": "0", "N1": "1", "N2": "2", "N3": "3", "N4": "4",
    "N5": "5", "N6": "6", "N7": "7", "N8": "8", "N9": "9",
    "K_POWER": "Power", "INS": "Ins", "DEL": "Del", "CAPS": "Caps",
    "PSCRN": "PrtSc", "SLCK": "ScrLk", "PAUSE_BREAK": "Pause",
    "KP_NUM": "NumLk", "UP": "↑", "DOWN": "↓", "LEFT": "←",
    "RIGHT": "→", "HOME": "Home", "END": "End", "PG_UP": "PgUp",
    "PG_DN": "PgDn", "C_VOL_DN": "Vol-", "C_VOL_UP": "Vol+", "C_MUTE": "Mute",
    "C_EJECT": "Eject", "C_PREV": "Prev", "C_PP": "Play", "C_STOP": "Stop",
    "C_NEXT": "Next", "KP_MULTIPLY": "KP*", "KP_DIVIDE": "KP/",
    "KP_ENTER": "KPEnter", "KP_PLUS": "KP+", "KP_MINUS": "KP-",
}


def label(binding):
    binding = binding.strip()
    if binding == "&trans":
        return ""
    if binding.startswith("&kp "):
        code = binding[len("&kp "):].strip()
        if code in KP_LABELS:
            return KP_LABELS[code]
        if re.fullmatch(r"F\d{1,2}", code):
            return code
        if re.fullmatch(r"[A-Z]", code):
            return code
        return code
    if binding.startswith("&mo "):
        return "Fn"
    if binding.startswith("&bt BT_SEL"):
        return "BT" + binding.rsplit(" ", 1)[-1]
    if binding == "&bt BT_CLR":
        return "BT Clr"
    if binding == "&bootloader":
        return "Boot"
    if binding == "&sys_reset":
        return "Reset"
    if binding == "&studio_unlock":
        return "Studio"
    return binding


def svg_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_svg(keys, bindings, title):
    """Return the SVG text for one layer, without touching disk.

    Kept separate from `render` below so callers that only want to compare
    generated content against a committed file (tools/validate_shield.py)
    never need to write anything out to do so.
    """
    max_x = max(x + w for w, h, x, y in keys)
    max_y = max(y + h for w, h, x, y in keys)
    width = max_x * SCALE + 20
    height = max_y * SCALE + 40

    parts = []
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 0 %.1f %.1f" font-family="Menlo, Consolas, monospace">'
        % (width, height)
    )
    parts.append(
        '<rect x="0" y="0" width="%.1f" height="%.1f" fill="#1e1e1e"/>' % (width, height)
    )
    parts.append(
        '<text x="10" y="20" fill="#e0e0e0" font-size="14" font-weight="bold">%s</text>'
        % svg_escape(title)
    )

    for (w, h, x, y), binding in zip(keys, bindings):
        rx = 10 + x * SCALE + GAP
        ry = 30 + y * SCALE + GAP
        rw = w * SCALE - 2 * GAP
        rh = h * SCALE - 2 * GAP
        text = label(binding)
        font_size = 9 if len(text) > 5 else 11
        parts.append(
            '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" '
            'fill="#3a3a3a" stroke="#666" stroke-width="1"/>'
            % (rx, ry, rw, rh)
        )
        if text:
            parts.append(
                '<text x="%.1f" y="%.1f" fill="#f0f0f0" font-size="%d" '
                'text-anchor="middle" dominant-baseline="middle">%s</text>'
                % (rx + rw / 2, ry + rh / 2, font_size, svg_escape(text))
            )
    parts.append("</svg>")

    return "\n".join(parts) + "\n"


def render(name, keys, bindings, title):
    svg = render_svg(keys, bindings, title)
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, name)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(svg)
    print("wrote", os.path.relpath(out_path, vs.REPO))


def main():
    keys = vs.layout_keys()
    layers = vs.keymap_layers()
    render("base-layer.svg", keys, layers[0], "Unix60 - Base layer")
    render("fn-layer.svg", keys, layers[1], "Unix60 - Fn layer")


if __name__ == "__main__":
    main()
