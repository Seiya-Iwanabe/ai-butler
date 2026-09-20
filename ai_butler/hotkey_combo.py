"""Pure parsing of a hotkey combo string into (modifier mask, keycode).

No macOS/Quartz dependency here on purpose, so this logic is unit-testable
on any platform -- see hotkey.py for why it exists and what uses it.

Keycodes below are macOS virtual keycodes (`kVK_*` in Carbon's
HIToolbox/Events.h): they identify a physical key position and are stable
across keyboard layouts, unlike a character. That's what lets hotkey.py
avoid ever needing layout-dependent, TSM-backed keycode-to-character
translation.
"""

from __future__ import annotations

from typing import Tuple

# macOS virtual keycodes for the small set of keys ai_butler's hotkey needs
# to support. Extend this table if you need a key that isn't here.
KEY_CODES = {
    "space": 49,
    "a": 0, "b": 11, "c": 8, "d": 2, "e": 14, "f": 3, "g": 5, "h": 4,
    "i": 34, "j": 38, "k": 40, "l": 37, "m": 46, "n": 45, "o": 31, "p": 35,
    "q": 12, "r": 15, "s": 1, "t": 17, "u": 32, "v": 9, "w": 13, "x": 7,
    "y": 16, "z": 6,
    "0": 29, "1": 18, "2": 19, "3": 20, "4": 21, "5": 23, "6": 22, "7": 26,
    "8": 28, "9": 25,
    "escape": 53, "return": 36, "tab": 48, "delete": 51,
    "up": 126, "down": 125, "left": 123, "right": 124,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
    "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
}  # fmt: skip

# Bit values below match CGEventFlags' kCGEventFlagMask* constants, which
# are long-standing, stable, publicly documented Apple constants
# (CGEventTypes.h: alphaShift=1<<16, shift=1<<17, control=1<<18,
# alternate=1<<19, command=1<<20). Duplicated here as plain ints rather
# than imported from Quartz so this module has no Quartz dependency and
# stays importable/testable on any platform.
MODIFIER_FLAGS = {
    "alt": 1 << 19,       # kCGEventFlagMaskAlternate
    "option": 1 << 19,
    "cmd": 1 << 20,        # kCGEventFlagMaskCommand
    "command": 1 << 20,
    "ctrl": 1 << 18,        # kCGEventFlagMaskControl
    "control": 1 << 18,
    "shift": 1 << 17,        # kCGEventFlagMaskShift
}

# Only these bits are compared when matching an incoming event, so caps
# lock / numeric-pad / function-key / device-dependent flag bits (which
# macOS also reports) never prevent a match.
RELEVANT_FLAGS_MASK = (
    MODIFIER_FLAGS["alt"]
    | MODIFIER_FLAGS["cmd"]
    | MODIFIER_FLAGS["ctrl"]
    | MODIFIER_FLAGS["shift"]
)


class HotkeyParseError(ValueError):
    """Raised when a hotkey combo string can't be parsed."""


def parse_combo(combo: str) -> Tuple[int, int]:
    """Parse e.g. "<alt>+<space>" or "alt+space" into (modifier_mask, keycode)."""
    parts = [p.strip().strip("<>").lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise HotkeyParseError(f"空のホットキー指定です: {combo!r}")

    modifier_mask = 0
    key_parts = []
    for part in parts:
        if part in MODIFIER_FLAGS:
            modifier_mask |= MODIFIER_FLAGS[part]
        else:
            key_parts.append(part)

    if len(key_parts) != 1:
        raise HotkeyParseError(
            f"ホットキー指定 {combo!r} は「修飾キー+キー1つ」の形式にしてください"
            f"(例: <alt>+<space>)。対応キー: {', '.join(sorted(KEY_CODES))}"
        )

    key_name = key_parts[0]
    if key_name not in KEY_CODES:
        raise HotkeyParseError(
            f"キー '{key_name}' は未対応です。対応キー: {', '.join(sorted(KEY_CODES))}"
        )

    if modifier_mask == 0:
        raise HotkeyParseError(
            f"ホットキー指定 {combo!r} に修飾キー(alt/cmd/ctrl/shift)がありません"
        )

    return modifier_mask, KEY_CODES[key_name]
