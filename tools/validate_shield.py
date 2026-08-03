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
    Handles comments between the property name and `=`.
    """
    start = re.search(r"(?<![\w-])" + re.escape(prop) + r"(?:[^=]*?)=\s*<", text)
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


def main():
    check_matrix()
    check_transform()
    check_layout()

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
