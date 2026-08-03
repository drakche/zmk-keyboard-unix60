#!/usr/bin/env python3
"""Static consistency checks for the Unix60 ZMK shield.

Devicetree describes fixed hardware, so there is nothing to unit test in the
usual sense. What can go wrong is transcription: a miscounted row, a transposed
pin, a duplicated matrix position, geometry that drifts out of alignment. These
checks catch that class of error without a Zephyr toolchain.

Run from the repo root:  python3 tools/validate_shield.py
"""

import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIELD = "boards/shields/unix60"

ROWS = 7
COLS = 9
KEY_COUNT = 60
ROW_LENGTHS = [15, 14, 13, 13, 5]

RESULTS = []


def read(rel_path):
    with open(os.path.join(REPO, rel_path), encoding="utf-8") as handle:
        return handle.read()


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def dt_property(text, prop):
    """Return the raw text between `prop = <` and its matching `>`.

    The lookbehind stops `map` from matching inside `gpio-map`.
    Handles // comments between property name and `=`.
    """
    start = re.search(
        r"(?<![\w-])" + re.escape(prop) + r"(?:\s*//[^\n]*)?\s*=\s*<", text
    )
    if not start:
        raise ValueError("property %r not found" % prop)
    index = start.end()
    depth = 1
    while depth:
        char = text[index]
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
            if not depth:
                break
        index += 1
    return text[start.end():index]


def gpio_pins(text, prop):
    """Return the pro_micro pin numbers listed in a *-gpios property."""
    body = re.search(
        re.escape(prop) + r"\s*=\s*(.*?);", text, re.S
    )
    if not body:
        raise ValueError("property %r not found" % prop)
    return [int(n) for n in re.findall(r"&pro_micro\s+(\d+)", body.group(1))]


def transform_entries():
    text = read(SHIELD + "/unix60.overlay")
    return [
        (int(r), int(c))
        for r, c in re.findall(r"RC\(\s*(\d+)\s*,\s*(\d+)\s*\)", dt_property(text, "map"))
    ]


def check_matrix():
    text = read(SHIELD + "/unix60.overlay")

    check(
        "overlay uses only the &pro_micro nexus",
        not re.search(r"&gpio[01]\b", text),
        "found a direct &gpio0/&gpio1 reference",
    )
    check(
        'diode-direction is "col2row"',
        'diode-direction = "col2row"' in text,
    )
    check("kscan declares wakeup-source", "wakeup-source" in text)

    rows = gpio_pins(text, "row-gpios")
    cols = gpio_pins(text, "col-gpios")
    check("row-gpios pins", rows == [1, 0, 2, 3, 4, 5, 6], "got %r" % (rows,))
    check("col-gpios pins", cols == [7, 8, 9, 21, 20, 19, 18, 15, 14], "got %r" % (cols,))

    row_flags = re.findall(r"&pro_micro\s+\d+\s+\(([^)]*)\)", text)
    check(
        "every row gpio has ACTIVE_HIGH | PULL_DOWN",
        len(row_flags) == ROWS
        and all("GPIO_ACTIVE_HIGH" in f and "GPIO_PULL_DOWN" in f for f in row_flags),
        "got %r" % (row_flags,),
    )

    col_body = re.search(r"col-gpios\s*=\s*(.*?);", text, re.S)
    if col_body:
        col_flags = re.findall(r"<\s*&pro_micro\s+\d+\s+([^>]+)\s*>", col_body.group(1))
        check(
            "every col-gpios is bare GPIO_ACTIVE_HIGH",
            len(col_flags) == COLS
            and all(f.strip() == "GPIO_ACTIVE_HIGH" for f in col_flags),
            "got %r" % (col_flags,),
        )

    declared_rows = int(re.search(r"rows\s*=\s*<\s*(\d+)", text).group(1))
    declared_cols = int(re.search(r"columns\s*=\s*<\s*(\d+)", text).group(1))
    check("transform rows matches row-gpios count", declared_rows == len(rows) == ROWS)
    check("transform columns matches col-gpios count", declared_cols == len(cols) == COLS)


def check_transform():
    entries = transform_entries()

    check("transform has 60 entries", len(entries) == KEY_COUNT, "got %d" % len(entries))
    out_of_range = [e for e in entries if not (0 <= e[0] < ROWS and 0 <= e[1] < COLS)]
    check("every RC() is within 7x9", not out_of_range, "out of range: %r" % (out_of_range,))

    duplicates = sorted({e for e in entries if entries.count(e) > 1})
    check("no duplicate RC()", not duplicates, "duplicated: %r" % (duplicates,))

    # The three positions the Unix60 PCB reserves for alternate layouts.
    unused = sorted(
        {(r, c) for r in range(ROWS) for c in range(COLS)} - set(entries)
    )
    check(
        "exactly the three alternate-layout positions are unused",
        unused == [(1, 5), (4, 6), (5, 0)],
        "unused: %r" % (unused,),
    )


def layout_keys():
    text = read(SHIELD + "/unix60-layouts.dtsi")
    # Find the entire keys property: from `keys` to the terminating `;`
    # Handle both single-bracket form `= <...>` and comma-separated form `= <...>, <...>`.
    match = re.search(
        r"(?<![\w-])keys\s*(?://[^\n]*)?\s*=\s*(.*?);", text, re.S
    )
    if not match:
        raise ValueError("keys property not found")
    body = match.group(1)

    # Extract all <...> groups and concatenate them
    # This handles both = <...> and = <...>, <...> forms.
    bracket_bodies = []
    for bracket_match in re.finditer(r"<(.*?)>", body, re.S):
        bracket_bodies.append(bracket_match.group(1))
    full_body = " ".join(bracket_bodies)

    return [
        tuple(int(n) for n in m[:4])
        for m in re.findall(
            r"&key_physical_attrs\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
            full_body,
        )
    ]


# QMK keycode -> ZMK binding. Every keycode used by unix60.json appears here.
QMK_TO_ZMK = {
    "KC_TRNS": "&trans",
    "KC_ESC": "&kp ESC", "KC_GRV": "&kp GRAVE", "KC_MINS": "&kp MINUS",
    "KC_EQL": "&kp EQUAL", "KC_BSLS": "&kp BSLH", "KC_TAB": "&kp TAB",
    "KC_LBRC": "&kp LBKT", "KC_RBRC": "&kp RBKT", "KC_BSPC": "&kp BSPC",
    "KC_LCTL": "&kp LCTRL", "KC_SCLN": "&kp SEMI", "KC_QUOT": "&kp SQT",
    "KC_ENT": "&kp RET", "KC_LSFT": "&kp LSHFT", "KC_COMM": "&kp COMMA",
    "KC_DOT": "&kp DOT", "KC_SLSH": "&kp FSLH", "KC_RSFT": "&kp RSHFT",
    "KC_LALT": "&kp LALT", "KC_LGUI": "&kp LGUI", "KC_SPC": "&kp SPACE",
    "KC_RGUI": "&kp RGUI", "KC_RALT": "&kp RALT",
    "MO(1)": "&mo 1",
    # Fn layer
    "KC_PWR": "&kp K_POWER", "KC_INS": "&kp INS", "KC_DEL": "&kp DEL",
    "KC_CAPS": "&kp CAPS", "KC_PSCR": "&kp PSCRN", "KC_SCRL": "&kp SLCK",
    "KC_PAUS": "&kp PAUSE_BREAK", "KC_NUM": "&kp KP_NUM",
    "KC_UP": "&kp UP", "KC_DOWN": "&kp DOWN",
    "KC_LEFT": "&kp LEFT", "KC_RGHT": "&kp RIGHT",
    "KC_HOME": "&kp HOME", "KC_END": "&kp END",
    "KC_PGUP": "&kp PG_UP", "KC_PGDN": "&kp PG_DN",
    "KC_VOLD": "&kp C_VOL_DN", "KC_VOLU": "&kp C_VOL_UP",
    "KC_MUTE": "&kp C_MUTE", "KC_EJCT": "&kp C_EJECT",
    "KC_MPRV": "&kp C_PREV", "KC_MPLY": "&kp C_PP",
    "KC_MSTP": "&kp C_STOP", "KC_MNXT": "&kp C_NEXT",
    "KC_PAST": "&kp KP_MULTIPLY", "KC_PSLS": "&kp KP_DIVIDE",
    "KC_PENT": "&kp KP_ENTER", "KC_PPLS": "&kp KP_PLUS",
    "KC_PMNS": "&kp KP_MINUS",
}

# Wireless keys substituted into &trans slots on the Fn layer. Position -> binding.
FN_SUBSTITUTIONS = {
    16: "&bt BT_SEL 0",   # Q
    17: "&bt BT_SEL 1",   # W
    18: "&bt BT_SEL 2",   # E
    19: "&bt BT_SEL 3",   # R
    20: "&bt BT_SEL 4",   # T
    21: "&bt BT_CLR",     # Y
    22: "&bootloader",    # U
    27: "&sys_reset",     # ]
}


def qmk_to_zmk(code):
    if code.startswith("KC_F") and code[4:].isdigit():
        return "&kp F" + code[4:]
    if re.fullmatch(r"KC_[A-Z]", code):
        return "&kp " + code[3:]
    if re.fullmatch(r"KC_[0-9]", code):
        return "&kp N" + code[3:]
    return QMK_TO_ZMK[code]


def keymap_layers():
    """Return the bindings of each keymap layer, as lists of strings."""
    text = read(SHIELD + "/unix60.keymap")
    layers = []
    for block in re.findall(r"bindings\s*=\s*<(.*?)>\s*;", text, re.S):
        code = re.sub(r"//[^\n]*", " ", block)
        tokens = code.split()
        bindings, current = [], None
        for token in tokens:
            if token.startswith("&"):
                if current:
                    bindings.append(" ".join(current))
                current = [token]
            elif current:
                current.append(token)
        if current:
            bindings.append(" ".join(current))
        layers.append(bindings)
    return layers


def check_keymap():
    text = read(SHIELD + "/unix60.keymap")
    layers = keymap_layers()
    source = json.loads(read("unix60.json"))["layers"]

    check("keymap includes behaviors.dtsi", "#include <behaviors.dtsi>" in text)
    check("keymap includes keys.h", "dt-bindings/zmk/keys.h" in text)
    check("keymap includes bt.h", "dt-bindings/zmk/bt.h" in text)
    check("keymap has 2 layers", len(layers) == 2, "got %d" % len(layers))

    if len(layers) != 2:
        return

    for index, bindings in enumerate(layers):
        check(
            "layer %d has 60 bindings" % index,
            len(bindings) == KEY_COUNT,
            "got %d" % len(bindings),
        )

    expected_base = [qmk_to_zmk(code) for code in source[0]]
    check(
        "layer 0 matches unix60.json exactly",
        layers[0] == expected_base,
        "first mismatch: %r" % (
            next(
                (
                    (i, got, want)
                    for i, (got, want) in enumerate(zip(layers[0], expected_base))
                    if got != want
                ),
                None,
            ),
        ),
    )

    expected_fn = [qmk_to_zmk(code) for code in source[1]]
    for position, binding in FN_SUBSTITUTIONS.items():
        check(
            "Fn position %d was a &trans slot before substitution" % position,
            expected_fn[position] == "&trans",
            "unix60.json has %r there" % source[1][position],
        )
        expected_fn[position] = binding
    check(
        "layer 1 matches unix60.json plus the 8 wireless keys",
        layers[1] == expected_fn,
        "first mismatch: %r" % (
            next(
                (
                    (i, got, want)
                    for i, (got, want) in enumerate(zip(layers[1], expected_fn))
                    if got != want
                ),
                None,
            ),
        ),
    )
    check(
        "exactly 8 wireless keys were substituted",
        len(FN_SUBSTITUTIONS) == 8,
    )


def check_layout():
    text = read(SHIELD + "/unix60-layouts.dtsi")
    keys = layout_keys()

    check("layout node is named unix60_layout", "unix60_layout:" in text)
    check("layout binds the transform", "transform = <&default_transform>" in text)
    check("layout binds the kscan", "kscan = <&kscan>" in text)
    check("layout has 60 keys", len(keys) == KEY_COUNT, "got %d" % len(keys))
    check(
        "layout key count equals transform entry count",
        len(keys) == len(transform_entries()),
    )

    # Group keys by their y coordinate, preserving order.
    rows = []
    for w, h, x, y in keys:
        if not rows or rows[-1][0] != y:
            rows.append((y, []))
        rows[-1][1].append((x, w))

    check(
        "layout has 5 rows at y = 0,100,200,300,400",
        [y for y, _ in rows] == [0, 100, 200, 300, 400],
        "got %r" % ([y for y, _ in rows],),
    )
    check(
        "row key counts are 15/14/13/13/5",
        [len(r) for _, r in rows] == ROW_LENGTHS,
        "got %r" % ([len(r) for _, r in rows],),
    )

    # Every key must start exactly where the previous one ended.
    gaps = []
    for _, (y, row) in enumerate(rows):
        for (x1, w1), (x2, _) in zip(row, row[1:]):
            if x1 + w1 != x2:
                gaps.append((y, x1, x1 + w1, x2))
    check("no gaps or overlaps within any row", not gaps, "at %r" % (gaps,))

    # Check row spans only if we have the expected 5 rows.
    if len(rows) >= 5:
        spans = [(row[0][0], row[-1][0] + row[-1][1]) for _, row in rows]
        check(
            "rows 0-3 span 0 to 1500",
            all(s == (0, 1500) for s in spans[:4]),
            "got %r" % (spans[:4],),
        )
        check(
            "row 4 spans 150 to 1350, leaving 1.5u blockers",
            spans[4] == (150, 1350),
            "got %r" % (spans[4],),
        )
    else:
        check("rows 0-3 span 0 to 1500", False, "only %d rows" % len(rows))
        check(
            "row 4 spans 150 to 1350, leaving 1.5u blockers",
            False,
            "only %d rows" % len(rows),
        )

    check("every key is 100 units tall", all(h == 100 for _, h, _, _ in keys))


def check_metadata():
    meta = read(SHIELD + "/unix60.zmk.yml")
    check("metadata id is unix60", re.search(r"^id:\s*unix60\s*$", meta, re.M))
    check("metadata type is shield", re.search(r"^type:\s*shield\s*$", meta, re.M))
    check(
        "metadata url points at the Unix60 project",
        "github.com/mkdl/Unix60" in meta,
    )
    check("metadata requires pro_micro", re.search(r"-\s*pro_micro", meta))
    check("metadata declares the keys feature", re.search(r"-\s*keys", meta))
    check("metadata declares the studio feature", re.search(r"-\s*studio", meta))
    check(
        "metadata no longer contains template placeholders",
        "example.com" not in meta and "generated from a template" not in meta,
    )

    conf = read(SHIELD + "/unix60.conf")
    check(
        "conf has no uncommented settings",
        not [
            line
            for line in conf.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ],
        "shield defaults belong in Kconfig.defconfig, not unix60.conf",
    )

    readme = read(SHIELD + "/README.md")
    for topic in ("pro_micro", "col2row", "P0.24", "RC(1,5)"):
        check("README documents %s" % topic, topic in readme)

    build = read("build.yaml")
    check("build.yaml targets nice_nano_v2", "nice_nano_v2" in build)
    check(
        "build.yaml has a plain unix60 entry",
        re.search(r"-\s*board:\s*nice_nano_v2\s*\n\s*shield:\s*unix60\s*\n\s*-", build),
    )
    check("build.yaml has a studio entry", "studio-rpc-usb-uart" in build)
    check("build.yaml studio entry sets CONFIG_ZMK_STUDIO", "-DCONFIG_ZMK_STUDIO=y" in build)
    check("build.yaml names the studio artifact", "artifact-name: unix60_studio" in build)


def check_completeness():
    """A file existing on disk is not enough — ZMK's CI only ever sees what
    git tracks. This is the check that catches a shield file being written
    but never `git add`ed, which every other check here is blind to."""
    tracked = set(
        subprocess.run(
            ["git", "ls-files", SHIELD],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    )
    required = [
        "Kconfig.shield",
        "Kconfig.defconfig",
        "unix60.overlay",
        "unix60-layouts.dtsi",
        "unix60.keymap",
        "unix60.conf",
        "unix60.zmk.yml",
    ]
    missing = [name for name in required if SHIELD + "/" + name not in tracked]
    check(
        "every file ZMK needs for the shield is tracked by git",
        not missing,
        "untracked: %r" % (missing,),
    )

    kconfig_shield = read(SHIELD + "/Kconfig.shield")
    check(
        "Kconfig.shield defines SHIELD_UNIX60",
        re.search(r"config\s+SHIELD_UNIX60\b", kconfig_shield) is not None,
    )

    kconfig_defconfig = read(SHIELD + "/Kconfig.defconfig")
    check(
        "Kconfig.defconfig sets ZMK_KEYBOARD_NAME guarded by if SHIELD_UNIX60",
        re.search(r"if\s+SHIELD_UNIX60\b", kconfig_defconfig) is not None
        and re.search(r"config\s+ZMK_KEYBOARD_NAME\b", kconfig_defconfig) is not None,
    )


def main():
    check_matrix()
    check_transform()
    check_layout()
    check_keymap()
    check_metadata()
    check_completeness()

    width = max(len(name) for name, _, _ in RESULTS)
    failed = 0
    for name, ok, detail in RESULTS:
        status = "PASS" if ok else "FAIL"
        line = "%-*s  %s" % (width, name, status)
        if not ok and detail:
            line += "  -- " + detail
        print(line)
        failed += not ok

    print()
    print("%d checks, %d failed" % (len(RESULTS), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
