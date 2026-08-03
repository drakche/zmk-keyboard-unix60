# Unix60 ZMK Shield — Design

Date: 2026-08-03

## Goal

Turn `boards/shields/unix60/` from the untouched `new-shield` template into a
complete, buildable ZMK shield for the FR4Boards Unix60, driven by a wireless
nRF52840 controller in the PCB's Pro Micro socket.

## Source of truth

Two inputs, with different roles:

- `unix60.json` (repo root) — a QMK Configurator *keymap* export for
  `fr4/unix60`, layout `LAYOUT_60_hhkb`, two layers. Supplies the keycodes.
  Contains no wiring information.
- QMK's `keyboards/fr4/unix60/keyboard.json` (fetched from qmk_firmware
  `master`) — supplies matrix pins, diode direction, and per-key matrix
  positions and geometry.

The Unix60 declares `"development_board": "promicro"`, which is what makes a ZMK
*shield* (rather than a board) the correct abstraction: the MCU is not on the
keyboard PCB.

## Target hardware

`nice_nano_v2`, standing in for the board silkscreened "Pro Micro nRF52840"
(also sold as "SuperMini nRF52840"), sourced from AliExpress listing
`1005007205026373`. Pin-compatible with the nice!nano v2 and built under that
target by the community.

The board has been reverse-engineered in
[sasodoma/nrf52840-promicro](https://github.com/sasodoma/nrf52840-promicro),
which supplies the two hardware facts below.

**Battery reporting works.** The battery connects directly to `VDDH`
(high-voltage mode), as on the nice!nano v2, and `nice_nano_v2.dts` selects
`compatible = "zmk,battery-nrf-vddh"` — internal VDDH sensing through the SoC,
using no GPIO. The clone's external battery divider is misrouted (silkscreened
`P0.04`, actually wired to `P0.24`, which has no ADC channel), but ZMK never
reads it, so the fault is inert. Voltage reads high while USB is connected;
that is also true of a genuine nice!nano.

**`P0.24` carries one extra onboard load, and it is a matrix row.** The
misrouted divider taps `P0.24` between R10 (to `VBAT`) and R11 (to `GND`).
`P0.24` is `pro_micro` pin 5, which the Unix60 hardwires to matrix row 5 —
the `Z X C V B N M ,` row. Cross-checking all 16 matrix pins against the
schematic's nets, `P0.24` is the only one with a connection beyond its
castellated pad.

This is assessed as low risk and is not designed around:

- The divider is high-impedance against the nRF52840's ~13k internal
  pull-down, so the row still idles low and still reads high when a column
  drives it.
- R10/R11 values are not recorded in the reverse-engineering and may not be
  populated at all. Even at 100k/100k the tap sits well under the logic
  threshold.
- It could not be designed around regardless: the Unix60 PCB fixes row 5 to
  that pad, so the shield cannot reassign it without cutting traces.

Residual risk to watch for on hardware: phantom or stuck keys confined to the
`Z`–`,` row. Removing R10 eliminates both that risk and the divider's parasitic
battery drain at no cost, since ZMK cannot use the divider anyway. Recommended
only if symptoms appear.

The shield is written against the `&pro_micro` nexus, not against `&gpio0`/
`&gpio1` directly, so it builds unchanged on any pro-micro-footprint board
(`nrfmicro`, `bluemicro840`, `puchi_ble_v1`, RP2040 pro micros). Only
`build.yaml` and the `requires:` metadata name a concrete board.

## Components

Seven files are rewritten or added; two stay exactly as generated.

| File | Action |
| --- | --- |
| `Kconfig.shield` | unchanged — template output is correct |
| `Kconfig.defconfig` | unchanged — sets `ZMK_KEYBOARD_NAME` to `Unix60` |
| `unix60.overlay` | rewrite — kscan + matrix transform |
| `unix60-layouts.dtsi` | rewrite — physical layout |
| `unix60.keymap` | rewrite — two layers |
| `unix60.conf` | rewrite — minimal, commented options |
| `unix60.zmk.yml` | rewrite — real metadata |
| `README.md` | new — provenance and pin mapping |
| `build.yaml` (repo root) | add two build entries |

### Matrix — `unix60.overlay`

7 rows x 9 columns, `diode-direction = "col2row"`. Columns are outputs,
rows are inputs with pull-downs, matching the in-tree `m60` shield.

| | QMK AVR pins | Pro Micro pins | GPIO flags |
| --- | --- | --- | --- |
| rows | `D3 D2 D1 D0 D4 C6 D7` | `1 0 2 3 4 5 6` | `GPIO_ACTIVE_HIGH \| GPIO_PULL_DOWN` |
| cols | `E6 B4 B5 F4 F5 F6 F7 B1 B3` | `7 8 9 21 20 19 18 15 14` | `GPIO_ACTIVE_HIGH` |

The AVR-to-Pro-Micro mapping is the standard ATmega32U4 Pro Micro pinout. All
sixteen resulting pins exist in the nice!nano `arduino_pro_micro_pins.dtsi`
nexus. Pro Micro pins 10 and 16 — the two that map to the nRF52840 NFC pins
`gpio0 9` and `gpio0 10`, and would need `CONFIG_NFCT_PINS_AS_GPIOS` — are not
used, so no NFC workaround is required.

### Matrix transform — `unix60.overlay`

The Unix60 matrix is serpentine: positions fill `RC(0,0)` through `RC(6,8)` in
visual reading order, disregarding physical rows. `columns = <9>`, `rows = <7>`.

```
RC(0,0) RC(0,1) RC(0,2) RC(0,3) RC(0,4) RC(0,5) RC(0,6) RC(0,7) RC(0,8) RC(1,0) RC(1,1) RC(1,2) RC(1,3) RC(1,4) RC(1,6)
RC(1,7) RC(1,8) RC(2,0) RC(2,1) RC(2,2) RC(2,3) RC(2,4) RC(2,5) RC(2,6) RC(2,7) RC(2,8) RC(3,0) RC(3,1) RC(3,2)
RC(3,3) RC(3,4) RC(3,5) RC(3,6) RC(3,7) RC(3,8) RC(4,0) RC(4,1) RC(4,2) RC(4,3) RC(4,4) RC(4,5) RC(4,7)
RC(4,8) RC(5,1) RC(5,2) RC(5,3) RC(5,4) RC(5,5) RC(5,6) RC(5,7) RC(5,8) RC(6,0) RC(6,1) RC(6,2) RC(6,3)
RC(6,4) RC(6,5) RC(6,6) RC(6,7) RC(6,8)
```

60 of the 63 matrix positions are used. The three unused ones are the PCB's
alternate-layout switch positions, documented in the README so they are not
mistaken for errors:

| Position | Alternate key it serves |
| --- | --- |
| `RC(1,5)` | 2u backspace (instead of split `\` + `` ` ``) |
| `RC(4,6)` | ISO `#` |
| `RC(5,0)` | split left shift / ISO backslash |

Supporting those alternates is explicitly out of scope. They are recorded only
so a future change has the data it needs.

### Physical layout — `unix60-layouts.dtsi`

A custom node `unix60_layout`, display name `60% HHKB (Unix60)`, holding
`transform` and `kscan` properties. `chosen` selects it as
`zmk,physical-layout`.

ZMK ships `layouts/common/60percent/hhkb.dtsi`, but that node is the
HHKB/*Tsangan* variant — 2u backspace, unsplit right shift, seven-key bottom
row, 60 keys in a different arrangement. The Unix60 is true HHKB. The built-in
layout is therefore **not** reused; geometry is transcribed from QMK's `x`/`y`/
`w` values, multiplied by 100.

```
row 0  y=0    15 x 1u at x=0…1400
row 1  y=100  1.5u Tab @0 │ 12 x 1u @150…1250 │ 1.5u Bspc @1350
row 2  y=200  1.75u Ctrl @0 │ 11 x 1u @175…1175 │ 2.25u Enter @1275
row 3  y=300  2.25u Shift @0 │ 10 x 1u @225…1125 │ 1.75u Shift @1225 │ 1u Fn @1400
row 4  y=400  1u Alt @150 │ 1.5u GUI @250 │ 7u Space @400 │ 1.5u GUI @1100 │ 1u Alt @1250
```

Key counts per row are 15 / 14 / 13 / 13 / 5, totalling 60, matching both the
QMK layout and the keymap. Every row spans 1500 units with no gaps or overlaps;
the bottom row leaves the expected 1.5u blockers at each end.

No position map is defined — there is only one physical layout, so there is
nothing to map between.

### Keymap — `unix60.keymap`

Both layers translate 1:1 from `unix60.json` in `LAYOUT_60_hhkb` order.
Every keycode in the export has a direct ZMK equivalent; the non-obvious ones
were verified to exist in `dt-bindings/zmk/keys.h`:

| QMK | ZMK | QMK | ZMK |
| --- | --- | --- | --- |
| `KC_PWR` | `K_POWER` | `KC_PAST` | `KP_MULTIPLY` |
| `KC_EJCT` | `C_EJECT` | `KC_PSLS` | `KP_DIVIDE` |
| `KC_SCRL` | `SLCK` | `KC_PENT` | `KP_ENTER` |
| `KC_NUM` | `KP_NUM` | `KC_PPLS` | `KP_PLUS` |
| `KC_PAUS` | `PAUSE_BREAK` | `KC_PMNS` | `KP_MINUS` |
| `KC_PSCR` | `PSCRN` | `KC_MPRV` | `C_PREV` |
| `KC_VOLD` / `KC_VOLU` | `C_VOL_DN` / `C_VOL_UP` | `KC_MPLY` | `C_PP` |
| `KC_MUTE` | `C_MUTE` | `KC_MSTP` / `KC_MNXT` | `C_STOP` / `C_NEXT` |

Routine mappings follow ZMK's usual names (`KC_BSLS`→`BSLH`, `KC_LBRC`→`LBKT`,
`KC_QUOT`→`SQT`, `KC_ENT`→`RET`, `KC_SLSH`→`FSLH`, `KC_GRV`→`GRAVE`,
`KC_1`→`N1`, and so on). `MO(1)` becomes `&mo 1`; `KC_TRNS` becomes `&trans`.

Wireless additions occupy `&trans` slots on the Fn layer only. Nothing defined
in the export is moved or overwritten:

| Fn-layer key | Binding |
| --- | --- |
| `Q` `W` `E` `R` `T` | `&bt BT_SEL 0` … `&bt BT_SEL 4` |
| `Y` | `&bt BT_CLR` |
| `U` | `&bootloader` |
| `]` | `&sys_reset` |

Rationale: without profile keys the keyboard can pair profile 0 but can never
switch or clear profiles, and without a reset key every flash means reaching
for the controller's physical button.

### Build — `build.yaml`

Two entries, both on `nice_nano_v2`:

1. `unix60` — plain build.
2. `unix60_studio` — adds `snippet: studio-rpc-usb-uart` and
   `cmake-args: -DCONFIG_ZMK_STUDIO=y`, with `artifact-name: unix60_studio`.

The plain build is retained as a smaller fallback, since Studio costs flash
space and requires USB.

`unix60.zmk.yml` declares `features: [keys, studio]`, `requires: [pro_micro]`,
and `url: https://github.com/mkdl/Unix60`.

## Testing

No local build is possible: `west` is not installed, there is no Zephyr SDK,
and `.zmk/` is the shallow editor-intellisense checkout — its `.west/config`
filters out `zephyr` and the HAL projects, so it is not a buildable tree.

Verification is therefore two-stage.

**Stage 1 — static validator.** A Python script, kept in the repo, that parses
the shield files and asserts:

1. Each keymap layer has exactly 60 bindings.
2. The transform map has exactly 60 entries.
3. Every `RC(r,c)` satisfies `r < 7` and `c < 9`.
4. No `RC(r,c)` appears twice in the transform.
5. The transform's declared `rows`/`columns` match the `row-gpios`/`col-gpios`
   counts.
6. The physical layout has exactly 60 `key_physical_attrs` entries — equal to
   the transform entry count.
7. Within each physical-layout row, consecutive keys are contiguous — no gaps
   and no overlaps. Rows 0-3 span the full 0 to 1500; row 4 spans 150 to 1350,
   leaving the 1.5u blockers at each end that the HHKB bottom row requires.
8. Every layer-0 and layer-1 binding corresponds to the expected translation of
   the same position in `unix60.json`, except at the eight positions where
   wireless keys were substituted for `&trans`.

This catches the realistic failure modes for hand-written devicetree —
miscounts, transposed pins, duplicated matrix positions, geometry drift. It does
not prove the files compile.

**Stage 2 — GitHub Actions.** Push the branch to `origin`
(`git@github.com:drakche/zmk-keyboard-unix60.git`). The repo's existing
`.github/workflows/build.yml` calls `zmkfirmware/zmk/.github/workflows/build-user-config.yml@v0.3`
and runs on `push`, so it compiles both build entries. This is the real proof.
Report the CI result and fix anything it catches.

The user has authorised this push.

## Out of scope

- Alternate physical layouts (2u backspace, ISO, split left shift), though the
  matrix positions that serve them are documented.
- RGB, encoders, displays, or any peripheral — the Unix60 has none that ZMK
  would drive.
- Tuning the keymap beyond the 1:1 port plus the eight wireless keys. Combos,
  hold-taps, and additional layers are the user's to add later.
- Any workaround for the misrouted `P0.24` battery divider. It is inert to ZMK,
  and the optional R10 removal is a hardware change for the user to make only
  if phantom keys appear on the `Z`–`,` row.
