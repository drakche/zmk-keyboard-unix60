# Unix60 ZMK Shield Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `new-shield` template in `boards/shields/unix60/` with a complete, buildable ZMK shield for the FR4Boards Unix60 driven by a Pro Micro nRF52840.

**Architecture:** Devicetree describes fixed hardware, so there is no application code and no unit-test framework. Correctness is enforced by a static validator (`tools/validate_shield.py`) that parses the shield files and asserts they are internally consistent and faithful to the two upstream sources. Each task adds validator checks *first*, watches them fail against the still-template files, then writes the devicetree to make them pass. Final proof of compilation comes from the repo's existing GitHub Actions workflow.

**Tech Stack:** ZMK v0.3 (Zephyr devicetree overlays, Kconfig), Python 3 standard library only (validator), GitHub Actions.

## Global Constraints

- Design spec: `docs/superpowers/specs/2026-08-03-unix60-zmk-shield-design.md`. Read it before starting.
- Target board is `nice_nano_v2`. The shield must reference GPIOs **only** through the `&pro_micro` nexus, never `&gpio0`/`&gpio1` directly, so it stays board-agnostic.
- Matrix is 7 rows x 9 columns, `diode-direction = "col2row"`. Columns are `GPIO_ACTIVE_HIGH`; rows are `(GPIO_ACTIVE_HIGH | GPIO_PULL_DOWN)`.
- Row pro_micro pins, in order: `1 0 2 3 4 5 6` (QMK `D3 D2 D1 D0 D4 C6 D7`).
- Column pro_micro pins, in order: `7 8 9 21 20 19 18 15 14` (QMK `E6 B4 B5 F4 F5 F6 F7 B1 B3`).
- Exactly 60 keys. Rows contain 15 / 14 / 13 / 13 / 5 keys.
- `Kconfig.shield` and `Kconfig.defconfig` are already correct. **Do not modify
  their contents** — but note they are UNTRACKED in git and must be committed.
  This wording originally said only "do not modify them", and every implementer
  correctly left them alone while nobody committed them; the first push shipped
  a shield with no `SHIELD_UNIX60` definition. Fixed in Task 5 fix round 1.
- Validator must use only the Python 3 standard library. No pip installs.
- Work directly on `main` and push to `origin main`. The user explicitly
  authorised this for this piece of work, overriding the usual branch-first
  rule, because the repo is new and has no other contributors.
- Every commit message ends with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `tools/validate_shield.py` | **Create.** All static consistency checks. Single responsibility: verify the unix60 shield files agree with each other and with the upstream sources. Grows across Tasks 1-4. |
| `boards/shields/unix60/unix60.overlay` | **Rewrite.** kscan node + matrix transform. |
| `boards/shields/unix60/unix60-layouts.dtsi` | **Rewrite.** Physical layout geometry only. |
| `boards/shields/unix60/unix60.keymap` | **Rewrite.** Two keymap layers. |
| `boards/shields/unix60/unix60.conf` | **Rewrite.** Commented user-tunable options. |
| `boards/shields/unix60/unix60.zmk.yml` | **Rewrite.** Hardware metadata. |
| `boards/shields/unix60/README.md` | **Create.** Provenance, pin mapping, hardware caveats. |
| `build.yaml` | **Modify.** Two build entries. |
| `boards/shields/unix60/Kconfig.shield` | Unchanged. |
| `boards/shields/unix60/Kconfig.defconfig` | Unchanged. |

Geometry and matrix data live in separate files because they answer different questions (where keys *are* vs how they are *wired*), and ZMK's template already splits them this way.

---

## Task 1: Validator foundation + matrix and transform

**Files:**
- Create: `tools/validate_shield.py`
- Modify: `boards/shields/unix60/unix60.overlay` (full rewrite)

**Interfaces:**
- Consumes: nothing (first task).
- Produces: for later tasks, `tools/validate_shield.py` exposes module-level helpers
  - `read(rel_path: str) -> str` — read a repo-relative file as text
  - `dt_property(text: str, prop: str) -> str` — return the raw contents between `prop = <` and the matching `>`
  - `check(name: str, ok: bool, detail: str = "") -> None` — record a result
  - `RESULTS: list[tuple[str, bool, str]]` — accumulated results
  - `ROWS = 7`, `COLS = 9`, `KEY_COUNT = 60`, `ROW_LENGTHS = [15, 14, 13, 13, 5]`
  - `SHIELD = "boards/shields/unix60"`
  - `transform_entries() -> list[tuple[int, int]]` — parsed `RC(r,c)` pairs from the overlay, in order

- [ ] **Step 1: Write the failing validator**

Create `tools/validate_shield.py`:

```python
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
    """
    start = re.search(r"(?<![\w-])" + re.escape(prop) + r"\s*=\s*<", text)
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


def main():
    check_matrix()
    check_transform()

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
```

- [ ] **Step 2: Run the validator to verify it fails**

Run: `python3 tools/validate_shield.py`

Expected: FAIL. The overlay is still the 2x2 template, so expect failures on
`row-gpios pins` (got `[0, 0]`), `col-gpios pins` (got `[0, 0]`),
`transform has 60 entries` (got 4), `transform rows matches row-gpios count`,
`transform columns matches col-gpios count`, and
`exactly the three alternate-layout positions are unused`.

- [ ] **Step 3: Write the overlay**

Replace `boards/shields/unix60/unix60.overlay` entirely:

```dts
/*
 * Copyright (c) 2026 The ZMK Contributors
 *
 * SPDX-License-Identifier: MIT
 */

#include <dt-bindings/zmk/matrix_transform.h>

#include "unix60-layouts.dtsi"

/ {
    chosen {
        zmk,physical-layout = &unix60_layout;
    };

    kscan: kscan {
        compatible = "zmk,kscan-gpio-matrix";
        diode-direction = "col2row";
        wakeup-source;

        /* QMK cols: E6 B4 B5 F4 F5 F6 F7 B1 B3 */
        col-gpios
            = <&pro_micro  7 GPIO_ACTIVE_HIGH>
            , <&pro_micro  8 GPIO_ACTIVE_HIGH>
            , <&pro_micro  9 GPIO_ACTIVE_HIGH>
            , <&pro_micro 21 GPIO_ACTIVE_HIGH>
            , <&pro_micro 20 GPIO_ACTIVE_HIGH>
            , <&pro_micro 19 GPIO_ACTIVE_HIGH>
            , <&pro_micro 18 GPIO_ACTIVE_HIGH>
            , <&pro_micro 15 GPIO_ACTIVE_HIGH>
            , <&pro_micro 14 GPIO_ACTIVE_HIGH>
            ;

        /* QMK rows: D3 D2 D1 D0 D4 C6 D7 */
        row-gpios
            = <&pro_micro  1 (GPIO_ACTIVE_HIGH | GPIO_PULL_DOWN)>
            , <&pro_micro  0 (GPIO_ACTIVE_HIGH | GPIO_PULL_DOWN)>
            , <&pro_micro  2 (GPIO_ACTIVE_HIGH | GPIO_PULL_DOWN)>
            , <&pro_micro  3 (GPIO_ACTIVE_HIGH | GPIO_PULL_DOWN)>
            , <&pro_micro  4 (GPIO_ACTIVE_HIGH | GPIO_PULL_DOWN)>
            , <&pro_micro  5 (GPIO_ACTIVE_HIGH | GPIO_PULL_DOWN)>
            , <&pro_micro  6 (GPIO_ACTIVE_HIGH | GPIO_PULL_DOWN)>
            ;
    };

    default_transform: keymap_transform_0 {
        compatible = "zmk,matrix-transform";
        columns = <9>;
        rows = <7>;

        /*
         * The Unix60 matrix is serpentine: positions fill RC(0,0) through
         * RC(6,8) in visual reading order, disregarding physical rows.
         * RC(1,5), RC(4,6) and RC(5,0) are the PCB's alternate-layout
         * positions (2u backspace, ISO #, split left shift) and are unused
         * by this layout.
         */
        map = <
RC(0,0) RC(0,1) RC(0,2) RC(0,3) RC(0,4) RC(0,5) RC(0,6) RC(0,7) RC(0,8) RC(1,0) RC(1,1) RC(1,2) RC(1,3) RC(1,4) RC(1,6)
RC(1,7) RC(1,8) RC(2,0) RC(2,1) RC(2,2) RC(2,3) RC(2,4) RC(2,5) RC(2,6) RC(2,7) RC(2,8) RC(3,0) RC(3,1) RC(3,2)
RC(3,3) RC(3,4) RC(3,5) RC(3,6) RC(3,7) RC(3,8) RC(4,0) RC(4,1) RC(4,2) RC(4,3) RC(4,4) RC(4,5) RC(4,7)
RC(4,8) RC(5,1) RC(5,2) RC(5,3) RC(5,4) RC(5,5) RC(5,6) RC(5,7) RC(5,8) RC(6,0) RC(6,1) RC(6,2) RC(6,3)
RC(6,4) RC(6,5) RC(6,6) RC(6,7) RC(6,8)
        >;
    };
};
```

The `#include "unix60-layouts.dtsi"` sits above the definitions of
`&unix60_layout`, `&default_transform` and `&kscan`. That is fine — devicetree
resolves labels after the whole tree is parsed, and ZMK's own template does the
same.

- [ ] **Step 4: Run the validator to verify matrix and transform checks pass**

Run: `python3 tools/validate_shield.py`

Expected: every check listed so far reports PASS, and the summary reads
`13 checks, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add tools/validate_shield.py boards/shields/unix60/unix60.overlay
git commit -m "$(cat <<'EOF'
Add shield validator and the Unix60 matrix and transform

Matrix pins and the serpentine transform come from QMK's fr4/unix60
keyboard.json, with AVR pins mapped onto the pro_micro nexus.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Physical layout

**Files:**
- Modify: `tools/validate_shield.py` (add `check_layout`, call it from `main`)
- Modify: `boards/shields/unix60/unix60-layouts.dtsi` (full rewrite)

**Interfaces:**
- Consumes: `read`, `check`, `dt_property`, `transform_entries`, `SHIELD`, `KEY_COUNT`, `ROW_LENGTHS` from Task 1.
- Produces: `layout_keys() -> list[tuple[int, int, int, int]]` — `(w, h, x, y)` per key, in order, for any later task that needs geometry.

- [ ] **Step 1: Write the failing layout checks**

Add to `tools/validate_shield.py`, above `main`:

```python
def layout_keys():
    text = read(SHIELD + "/unix60-layouts.dtsi")
    body = dt_property(text, "keys")
    return [
        tuple(int(n) for n in m[:4])
        for m in re.findall(
            r"&key_physical_attrs\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
            body,
        )
    ]


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
    for index, (y, row) in enumerate(rows):
        for (x1, w1), (x2, _) in zip(row, row[1:]):
            if x1 + w1 != x2:
                gaps.append((y, x1, x1 + w1, x2))
    check("no gaps or overlaps within any row", not gaps, "at %r" % (gaps,))

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
    check("every key is 100 units tall", all(h == 100 for _, h, _, _ in keys))
```

Then add `check_layout()` to `main`, immediately after `check_transform()`.

- [ ] **Step 2: Run the validator to verify the new checks fail**

Run: `python3 tools/validate_shield.py`

Expected: FAIL. The layouts file is still the 2x2 template, so expect
`layout node is named unix60_layout` to fail (the template calls it
`default_layout`), `layout has 60 keys` to fail with `got 4`, and the row
grouping, span and count checks to fail.

- [ ] **Step 3: Write the physical layout**

Replace `boards/shields/unix60/unix60-layouts.dtsi` entirely:

```dts
/*
 * Copyright (c) 2026 The ZMK Contributors
 *
 * SPDX-License-Identifier: MIT
 *
 * Geometry transcribed from QMK's fr4/unix60 LAYOUT_60_hhkb (x/y/w x 100).
 *
 * ZMK ships layouts/common/60percent/hhkb.dtsi, but that node is the
 * HHKB/Tsangan variant: 2u backspace, unsplit right shift, seven-key bottom
 * row. The Unix60 is true HHKB, so it needs its own layout.
 */

#include <physical_layouts.dtsi>

/ {
    unix60_layout: unix60_layout {
        compatible = "zmk,physical-layout";
        display-name = "60% HHKB (Unix60)";
        transform = <&default_transform>;
        kscan = <&kscan>;

        keys  //                     w   h    x    y     rot    rx    ry
            = <&key_physical_attrs 100 100    0    0       0     0     0>
            , <&key_physical_attrs 100 100  100    0       0     0     0>
            , <&key_physical_attrs 100 100  200    0       0     0     0>
            , <&key_physical_attrs 100 100  300    0       0     0     0>
            , <&key_physical_attrs 100 100  400    0       0     0     0>
            , <&key_physical_attrs 100 100  500    0       0     0     0>
            , <&key_physical_attrs 100 100  600    0       0     0     0>
            , <&key_physical_attrs 100 100  700    0       0     0     0>
            , <&key_physical_attrs 100 100  800    0       0     0     0>
            , <&key_physical_attrs 100 100  900    0       0     0     0>
            , <&key_physical_attrs 100 100 1000    0       0     0     0>
            , <&key_physical_attrs 100 100 1100    0       0     0     0>
            , <&key_physical_attrs 100 100 1200    0       0     0     0>
            , <&key_physical_attrs 100 100 1300    0       0     0     0>
            , <&key_physical_attrs 100 100 1400    0       0     0     0>
            , <&key_physical_attrs 150 100    0  100       0     0     0>
            , <&key_physical_attrs 100 100  150  100       0     0     0>
            , <&key_physical_attrs 100 100  250  100       0     0     0>
            , <&key_physical_attrs 100 100  350  100       0     0     0>
            , <&key_physical_attrs 100 100  450  100       0     0     0>
            , <&key_physical_attrs 100 100  550  100       0     0     0>
            , <&key_physical_attrs 100 100  650  100       0     0     0>
            , <&key_physical_attrs 100 100  750  100       0     0     0>
            , <&key_physical_attrs 100 100  850  100       0     0     0>
            , <&key_physical_attrs 100 100  950  100       0     0     0>
            , <&key_physical_attrs 100 100 1050  100       0     0     0>
            , <&key_physical_attrs 100 100 1150  100       0     0     0>
            , <&key_physical_attrs 100 100 1250  100       0     0     0>
            , <&key_physical_attrs 150 100 1350  100       0     0     0>
            , <&key_physical_attrs 175 100    0  200       0     0     0>
            , <&key_physical_attrs 100 100  175  200       0     0     0>
            , <&key_physical_attrs 100 100  275  200       0     0     0>
            , <&key_physical_attrs 100 100  375  200       0     0     0>
            , <&key_physical_attrs 100 100  475  200       0     0     0>
            , <&key_physical_attrs 100 100  575  200       0     0     0>
            , <&key_physical_attrs 100 100  675  200       0     0     0>
            , <&key_physical_attrs 100 100  775  200       0     0     0>
            , <&key_physical_attrs 100 100  875  200       0     0     0>
            , <&key_physical_attrs 100 100  975  200       0     0     0>
            , <&key_physical_attrs 100 100 1075  200       0     0     0>
            , <&key_physical_attrs 100 100 1175  200       0     0     0>
            , <&key_physical_attrs 225 100 1275  200       0     0     0>
            , <&key_physical_attrs 225 100    0  300       0     0     0>
            , <&key_physical_attrs 100 100  225  300       0     0     0>
            , <&key_physical_attrs 100 100  325  300       0     0     0>
            , <&key_physical_attrs 100 100  425  300       0     0     0>
            , <&key_physical_attrs 100 100  525  300       0     0     0>
            , <&key_physical_attrs 100 100  625  300       0     0     0>
            , <&key_physical_attrs 100 100  725  300       0     0     0>
            , <&key_physical_attrs 100 100  825  300       0     0     0>
            , <&key_physical_attrs 100 100  925  300       0     0     0>
            , <&key_physical_attrs 100 100 1025  300       0     0     0>
            , <&key_physical_attrs 100 100 1125  300       0     0     0>
            , <&key_physical_attrs 175 100 1225  300       0     0     0>
            , <&key_physical_attrs 100 100 1400  300       0     0     0>
            , <&key_physical_attrs 100 100  150  400       0     0     0>
            , <&key_physical_attrs 150 100  250  400       0     0     0>
            , <&key_physical_attrs 700 100  400  400       0     0     0>
            , <&key_physical_attrs 150 100 1100  400       0     0     0>
            , <&key_physical_attrs 100 100 1250  400       0     0     0>
            ;
    };
};
```

- [ ] **Step 4: Run the validator to verify the layout checks pass**

Run: `python3 tools/validate_shield.py`

Expected: all checks PASS, summary reads `24 checks, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add tools/validate_shield.py boards/shields/unix60/unix60-layouts.dtsi
git commit -m "$(cat <<'EOF'
Add the true-HHKB physical layout for the Unix60

Geometry transcribed from QMK's LAYOUT_60_hhkb. ZMK's in-tree
layout_60_hhkb is the Tsangan variant and would give a wrong 2u
backspace, unsplit right shift and seven-key bottom row.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Keymap

**Files:**
- Modify: `tools/validate_shield.py` (add `check_keymap`, call it from `main`)
- Modify: `boards/shields/unix60/unix60.keymap` (full rewrite)

**Interfaces:**
- Consumes: `read`, `check`, `dt_property`, `SHIELD`, `KEY_COUNT`, `ROW_LENGTHS` from Task 1.
- Produces: nothing consumed by later tasks.

This is the task where a silent error is most likely, because it is 120 hand-written bindings. The check therefore does not eyeball the keymap — it re-derives the expected bindings from `unix60.json` and compares.

- [ ] **Step 1: Write the failing keymap checks**

Add to `tools/validate_shield.py`, above `main`:

```python
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
```

Then add `check_keymap()` to `main`, immediately after `check_layout()`.

- [ ] **Step 2: Run the validator to verify the new checks fail**

Run: `python3 tools/validate_shield.py`

Expected: FAIL. The keymap is still the template, so expect
`keymap includes bt.h` to fail, `keymap has 2 layers` to fail with `got 1`, and
consequently an early return before the per-layer comparisons.

- [ ] **Step 3: Write the keymap**

Replace `boards/shields/unix60/unix60.keymap` entirely:

```dts
/*
 * Copyright (c) 2026 The ZMK Contributors
 *
 * SPDX-License-Identifier: MIT
 *
 * Ported 1:1 from unix60.json (QMK Configurator export, LAYOUT_60_hhkb).
 * The only additions are the Bluetooth, bootloader and reset keys, which
 * occupy slots the export left as KC_TRNS.
 */

#include <behaviors.dtsi>
#include <dt-bindings/zmk/keys.h>
#include <dt-bindings/zmk/bt.h>

/ {
    keymap {
        compatible = "zmk,keymap";

        default_layer {
// ---------------------------------------------------------------------------------------------
// | ESC |  1  |  2  |  3  |  4  |  5  |  6  |  7  |  8  |  9  |  0  |  -  |  =  |  \  |  `  |
// |  TAB   |  Q  |  W  |  E  |  R  |  T  |  Y  |  U  |  I  |  O  |  P  |  [  |  ]  |  BSPC  |
// |  CTRL    |  A  |  S  |  D  |  F  |  G  |  H  |  J  |  K  |  L  |  ;  |  '  |   ENTER    |
// |   SHIFT     |  Z  |  X  |  C  |  V  |  B  |  N  |  M  |  ,  |  .  |  /  | SHIFT  |  FN  |
// |        | ALT |  GUI   |               SPACE               |   GUI  | ALT |        |
// ---------------------------------------------------------------------------------------------
            bindings = <
&kp ESC   &kp N1 &kp N2 &kp N3 &kp N4 &kp N5 &kp N6 &kp N7 &kp N8 &kp N9 &kp N0 &kp MINUS &kp EQUAL &kp BSLH &kp GRAVE
&kp TAB   &kp Q  &kp W  &kp E  &kp R  &kp T  &kp Y  &kp U  &kp I  &kp O  &kp P  &kp LBKT  &kp RBKT  &kp BSPC
&kp LCTRL &kp A  &kp S  &kp D  &kp F  &kp G  &kp H  &kp J  &kp K  &kp L  &kp SEMI &kp SQT &kp RET
&kp LSHFT &kp Z  &kp X  &kp C  &kp V  &kp B  &kp N  &kp M  &kp COMMA &kp DOT &kp FSLH &kp RSHFT &mo 1
&kp LALT  &kp LGUI &kp SPACE &kp RGUI &kp RALT
            >;
        };

        fn_layer {
// ---------------------------------------------------------------------------------------------
// | PWR | F1  | F2  | F3  | F4  | F5  | F6  | F7  | F8  | F9  | F10 | F11 | F12 | INS | DEL |
// |  CAPS  | BT0 | BT1 | BT2 | BT3 | BT4 |BTCLR| BOOT| PSCR| SCRL|PAUSE|  UP |RESET|  NUM   |
// |          | VOLD| VOLU| MUTE| EJCT|     | KP* | KP/ | HOME| PGUP| LEFT|RIGHT|   KPENT    |
// |             |MPREV|MPLAY|MSTOP|MNEXT|     | KP+ | KP- | END | PGDN| DOWN|        |      |
// |        |     |        |                                   |        |     |        |
// ---------------------------------------------------------------------------------------------
            bindings = <
&kp K_POWER &kp F1 &kp F2 &kp F3 &kp F4 &kp F5 &kp F6 &kp F7 &kp F8 &kp F9 &kp F10 &kp F11 &kp F12 &kp INS &kp DEL
&kp CAPS    &bt BT_SEL 0 &bt BT_SEL 1 &bt BT_SEL 2 &bt BT_SEL 3 &bt BT_SEL 4 &bt BT_CLR &bootloader &kp PSCRN &kp SLCK &kp PAUSE_BREAK &kp UP &sys_reset &kp KP_NUM
&trans      &kp C_VOL_DN &kp C_VOL_UP &kp C_MUTE &kp C_EJECT &trans &kp KP_MULTIPLY &kp KP_DIVIDE &kp HOME &kp PG_UP &kp LEFT &kp RIGHT &kp KP_ENTER
&trans      &kp C_PREV &kp C_PP &kp C_STOP &kp C_NEXT &trans &kp KP_PLUS &kp KP_MINUS &kp END &kp PG_DN &kp DOWN &trans &trans
&trans      &trans &trans &trans &trans
            >;
        };
    };
};
```

- [ ] **Step 4: Run the validator to verify the keymap checks pass**

Run: `python3 tools/validate_shield.py`

Expected: all checks PASS, summary reads `41 checks, 0 failed`.

If `layer 0 matches unix60.json exactly` or
`layer 1 matches unix60.json plus the 8 wireless keys` fails, the detail column
prints `(position, got, want)` for the first mismatch. Fix the keymap to match
`want` — the JSON is the source of truth, not the hand-written table.

- [ ] **Step 5: Commit**

```bash
git add tools/validate_shield.py boards/shields/unix60/unix60.keymap
git commit -m "$(cat <<'EOF'
Port the Unix60 keymap from QMK to ZMK

Both layers translate 1:1 from unix60.json. Bluetooth profile keys,
bootloader and sys_reset occupy eight slots the export left as KC_TRNS,
so nothing defined in the export moves.

The validator re-derives both layers from unix60.json rather than
trusting the hand-written devicetree.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Metadata, config, README and build entries

**Files:**
- Modify: `tools/validate_shield.py` (add `check_metadata`, call it from `main`)
- Modify: `boards/shields/unix60/unix60.zmk.yml` (full rewrite)
- Modify: `boards/shields/unix60/unix60.conf` (full rewrite)
- Create: `boards/shields/unix60/README.md`
- Modify: `build.yaml`

**Interfaces:**
- Consumes: `read`, `check`, `SHIELD` from Task 1.
- Produces: nothing consumed by later tasks.

`unix60.zmk.yml` and `build.yaml` are YAML, but the validator may not assume
PyYAML is installed. Match on text instead.

- [ ] **Step 1: Write the failing metadata checks**

Add to `tools/validate_shield.py`, above `main`:

```python
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
```

Then add `check_metadata()` to `main`, immediately after `check_keymap()`.

- [ ] **Step 2: Run the validator to verify the new checks fail**

Run: `python3 tools/validate_shield.py`

Expected: FAIL, and it will raise `FileNotFoundError` on the missing
`README.md`. That is an acceptable red state — the next step creates it. If you
prefer a clean failure list, create an empty `README.md` first and re-run.

- [ ] **Step 3: Verify every Kconfig symbol before writing the conf file**

Do not write a `CONFIG_` name into `unix60.conf` without confirming it exists.

Run:

```bash
grep -rn "config ZMK_SLEEP$\|config ZMK_IDLE_SLEEP_TIMEOUT$\|config ZMK_EXT_POWER$" .zmk/zmk/app/
```

Keep only the symbols that this command actually finds, and drop any that it
does not. Note the comment lines below are illustrative defaults; adjust the
names to match what the grep confirms.

- [ ] **Step 4: Write the four files**

Replace `boards/shields/unix60/unix60.zmk.yml` entirely:

```yaml
file_format: "1"
id: unix60
name: Unix60
type: shield
url: https://github.com/mkdl/Unix60
requires:
  - pro_micro
features:
  - keys
  - studio
```

Replace `boards/shields/unix60/unix60.conf` entirely, keeping every line
commented — shield defaults belong in `Kconfig.defconfig`, and this file is
copied into the user's config directory as a starting point:

```
# Optional settings for the Unix60. Everything here is commented out by
# default; uncomment what you want.
#
# ZMK Studio is enabled per-build in build.yaml (it also needs the
# studio-rpc-usb-uart snippet), so it is deliberately not set here.

# Sleep after 15 minutes idle to save battery.
# CONFIG_ZMK_SLEEP=y
# CONFIG_ZMK_IDLE_SLEEP_TIMEOUT=900000
```

Create `boards/shields/unix60/README.md`:

```markdown
# Unix60

ZMK shield for the [FR4Boards Unix60](https://github.com/mkdl/Unix60), a 60%
HHKB-layout PCB that takes a Pro Micro footprint controller.

## Building

```bash
# Both firmware files are built by GitHub Actions on push; see build.yaml.
```

Two build entries are defined: `unix60` and `unix60_studio` (the latter adds
ZMK Studio, which lets you remap keys at runtime without recompiling).

## Hardware

- 7 rows x 9 columns, `diode-direction = "col2row"`.
- The matrix is **serpentine**: positions fill `RC(0,0)` through `RC(6,8)` in
  visual reading order, disregarding physical rows. This is why the transform
  map in `unix60.overlay` does not look like a grid.

| | QMK pins | pro_micro pins |
| --- | --- | --- |
| rows | `D3 D2 D1 D0 D4 C6 D7` | `1 0 2 3 4 5 6` |
| cols | `E6 B4 B5 F4 F5 F6 F7 B1 B3` | `7 8 9 21 20 19 18 15 14` |

60 of the 63 matrix positions are used. The three spare ones are the PCB's
alternate-layout switch positions, left unmapped on purpose:

| Position | Alternate key |
| --- | --- |
| `RC(1,5)` | 2u backspace, instead of split `\` + `` ` `` |
| `RC(4,6)` | ISO `#` |
| `RC(5,0)` | split left shift / ISO backslash |

## Physical layout

ZMK ships `layouts/common/60percent/hhkb.dtsi`, but that is the HHKB/*Tsangan*
variant: 2u backspace, unsplit right shift, seven-key bottom row. The Unix60 is
true HHKB, so `unix60-layouts.dtsi` defines its own layout, transcribed from
QMK's `LAYOUT_60_hhkb`.

## Note for Pro Micro nRF52840 (SuperMini) controllers

These nice!nano clones have a battery voltage divider that is silkscreened
`P0.04` but actually wired to `P0.24`
([reverse-engineering](https://github.com/sasodoma/nrf52840-promicro)). `P0.24`
has no ADC channel, so the divider is useless — but ZMK never reads it, because
`nice_nano_v2` measures the battery through the SoC's internal `VDDH` sensing.
Battery reporting works.

The catch: `P0.24` is `pro_micro` pin 5, which the Unix60 hardwires to matrix
row 5 — the `Z X C V B N M ,` row. The divider is high-impedance against the
nRF52840's internal pull-down, so this is expected to work. If you ever see
phantom or stuck keys **confined to that row**, the divider is the cause;
removing R10 on the controller fixes it at no cost.

## Provenance

- Matrix pins, diode direction and per-key matrix positions: QMK
  `keyboards/fr4/unix60/keyboard.json`.
- Keymap: `unix60.json` in the repo root, a QMK Configurator export for
  `LAYOUT_60_hhkb`.
- Run `python3 tools/validate_shield.py` from the repo root to check the shield
  files still agree with both sources.
```

Modify `build.yaml` — leave the existing explanatory comment block in place and
replace the trailing `---` line with:

```yaml
---
include:
  - board: nice_nano_v2
    shield: unix60
  - board: nice_nano_v2
    shield: unix60
    snippet: studio-rpc-usb-uart
    cmake-args: -DCONFIG_ZMK_STUDIO=y
    artifact-name: unix60_studio
```

- [ ] **Step 5: Run the validator to verify everything passes**

Run: `python3 tools/validate_shield.py`

Expected: all checks PASS, summary reads `58 checks, 0 failed`.

If `build.yaml has a plain unix60 entry` fails, the regex requires the plain
entry to be followed by another list item. Confirm the plain entry comes first
and the studio entry second.

- [ ] **Step 6: Commit**

```bash
git add tools/validate_shield.py boards/shields/unix60/unix60.zmk.yml \
        boards/shields/unix60/unix60.conf boards/shields/unix60/README.md build.yaml
git commit -m "$(cat <<'EOF'
Add Unix60 shield metadata, docs and build entries

build.yaml produces a plain unix60 firmware and a unix60_studio one.
The README records the serpentine matrix, the three unused
alternate-layout positions, and the P0.24 divider caveat for SuperMini
controllers.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Compile in CI

The validator proves the files agree with each other. It does not prove they
compile. This task gets that proof.

**Files:** none modified unless CI fails.

**Interfaces:**
- Consumes: a green validator run from Task 4.
- Produces: a CI conclusion, plus fixes if needed.

- [ ] **Step 1: Confirm the working tree is clean and the validator is green**

```bash
python3 tools/validate_shield.py && git status --short
```

Expected: `0 failed`, and no output from `git status --short`.

- [ ] **Step 2: Also commit the untracked repo-root files**

`.gitignore` and `unix60.json` are still untracked, and CI needs `unix60.json`
only as documentation — but leaving the tree dirty makes the CI result harder to
attribute. Commit them:

```bash
git add .gitignore unix60.json
git commit -m "$(cat <<'EOF'
Track the QMK keymap export and .gitignore

unix60.json is the source the keymap was ported from, and
tools/validate_shield.py reads it to verify the port.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Push the branch**

```bash
git push origin main
```

The user has authorised this push. The repo's
`.github/workflows/build.yml` runs on `push`, so this triggers a build of both
entries.

- [ ] **Step 4: Watch the run**

```bash
gh run list --branch main --limit 1
gh run watch "$(gh run list --branch main --limit 1 --json databaseId --jq '.[0].databaseId')" --exit-status
```

If `gh` is unavailable, poll instead:

```bash
gh --version || echo "Open https://github.com/drakche/zmk-unix-60/actions and report the result"
```

Expected: both matrix jobs succeed and upload `unix60` and `unix60_studio`
artifacts.

- [ ] **Step 5: Fix any failure, then re-verify**

Fetch the failing log:

```bash
gh run view "$(gh run list --branch main --limit 1 --json databaseId --jq '.[0].databaseId')" --log-failed
```

Devicetree errors most likely to appear here, and what they mean:

- `undefined reference to 'unix60_layout'` — the label in `unix60-layouts.dtsi`
  does not match `chosen { zmk,physical-layout = ... }` in the overlay.
- `'RC' undeclared` — `#include <dt-bindings/zmk/matrix_transform.h>` is missing
  from the overlay.
- `BT_SEL undeclared` — `#include <dt-bindings/zmk/bt.h>` is missing from the
  keymap.
- `keymap has N bindings, expected 60` or a physical-layout mismatch — the
  transform, layout and keymap disagree on key count; re-run the validator.
- `'&pro_micro' has no pin N` — a pin outside the nexus; cross-check against
  `.zmk/zmk/app/boards/arm/nice_nano/arduino_pro_micro_pins.dtsi`.

After any fix, re-run `python3 tools/validate_shield.py`, commit, push, and
watch again. Do not report success until CI is green.

- [ ] **Step 6: Report the outcome**

State plainly whether CI passed, and paste the artifact names. If it failed and
could not be fixed, say so and include the error.

---

## Self-Review

**1. Spec coverage.** Walking the spec section by section:

| Spec section | Task |
| --- | --- |
| Source of truth (both inputs) | Task 3 reads `unix60.json`; Tasks 1-2 encode `keyboard.json` data; Task 5 commits the JSON |
| Target hardware / `&pro_micro` only | Task 1, `overlay uses only the &pro_micro nexus` check |
| Battery reporting works | Task 4, README section |
| `P0.24` / row 5 caveat | Task 4, README section + `README documents P0.24` check |
| Matrix pins and flags | Task 1 |
| Matrix transform + 3 unused positions | Task 1 |
| Physical layout geometry | Task 2 |
| Keymap 1:1 + 8 wireless keys | Task 3 |
| `build.yaml` two entries | Task 4 |
| `unix60.zmk.yml` metadata | Task 4 |
| Testing stage 1 (validator, checks 1-8) | Tasks 1-4 |
| Testing stage 2 (GitHub Actions) | Task 5 |
| `Kconfig.*` unchanged | Global Constraints |
| Out of scope items | Not implemented, as intended |

Spec validator checks 1-8 map to: 1 → `layer N has 60 bindings`; 2 →
`transform has 60 entries`; 3 → `every RC() is within 7x9`; 4 →
`no duplicate RC()`; 5 → `transform rows/columns matches ... count`; 6 →
`layout key count equals transform entry count`; 7 →
`no gaps or overlaps within any row` plus the two span checks; 8 →
`layer 0/1 matches unix60.json`. All covered.

No gaps found.

**2. Placeholder scan.** No `TBD`, `TODO`, or "similar to Task N". Every code
step contains complete content. Two steps intentionally defer to a command's
output rather than hardcoding: Task 4 Step 3 greps for real Kconfig symbol names
before writing them, and Task 5 Step 5 reacts to CI output. Both are verification
steps with explicit commands and explicit criteria, not unfilled blanks.

**3. Type consistency.** Helper names are used consistently: `read`, `check`,
`dt_property`, `gpio_pins`, `transform_entries`, `layout_keys`, `keymap_layers`,
`qmk_to_zmk`, and the check functions `check_matrix`, `check_transform`,
`check_layout`, `check_keymap`, `check_metadata`. Constants `ROWS`, `COLS`,
`KEY_COUNT`, `ROW_LENGTHS`, `SHIELD`, `RESULTS`, `QMK_TO_ZMK`,
`FN_SUBSTITUTIONS` likewise. Devicetree labels agree across files:
`unix60_layout`, `default_transform`, `kscan` are defined in Tasks 1-2 and
referenced identically.

Cumulative check counts are 13 (Task 1: 9 matrix + 4 transform), 24 (+11
layout), 41 (+17 keymap) and 58 (+17 metadata). These are the expected totals
if every check is added as written; treat a mismatch as a signal that a check
was skipped or duplicated, not as a failure in itself.
