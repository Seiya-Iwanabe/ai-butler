import pytest

from ai_butler.hotkey_combo import (
    KEY_CODES,
    MODIFIER_FLAGS,
    HotkeyParseError,
    parse_combo,
)


def test_default_combo_option_space():
    mask, keycode = parse_combo("<alt>+<space>")
    assert mask == MODIFIER_FLAGS["alt"]
    assert keycode == KEY_CODES["space"]


def test_parses_without_angle_brackets():
    mask, keycode = parse_combo("alt+space")
    assert mask == MODIFIER_FLAGS["alt"]
    assert keycode == KEY_CODES["space"]


def test_is_case_insensitive():
    mask, keycode = parse_combo("<ALT>+<SPACE>")
    assert mask == MODIFIER_FLAGS["alt"]
    assert keycode == KEY_CODES["space"]


def test_multiple_modifiers_combine_with_or():
    mask, keycode = parse_combo("<cmd>+<shift>+<a>")
    assert mask == MODIFIER_FLAGS["cmd"] | MODIFIER_FLAGS["shift"]
    assert keycode == KEY_CODES["a"]


def test_option_and_alt_are_aliases():
    assert parse_combo("<option>+<space>") == parse_combo("<alt>+<space>")


def test_rejects_combo_with_no_key():
    with pytest.raises(HotkeyParseError):
        parse_combo("<alt>+<cmd>")


def test_rejects_combo_with_two_keys():
    with pytest.raises(HotkeyParseError):
        parse_combo("<alt>+<a>+<b>")


def test_rejects_unknown_key():
    with pytest.raises(HotkeyParseError, match="未対応"):
        parse_combo("<alt>+<unknownkey>")


def test_rejects_combo_with_no_modifier():
    with pytest.raises(HotkeyParseError, match="修飾キー"):
        parse_combo("<space>")


def test_rejects_empty_combo():
    with pytest.raises(HotkeyParseError):
        parse_combo("")
