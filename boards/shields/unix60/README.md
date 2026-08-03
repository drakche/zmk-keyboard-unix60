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
