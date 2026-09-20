"""Configuration loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - python-dotenv is an optional convenience
    load_dotenv = None  # type: ignore[assignment]

REALTIME_SAMPLE_RATE = 24000

# Confirmed against openai-python's generated Realtime API types
# (openai/types/realtime/realtime_audio_config_output_param.py) on 2026-09-20.
VALID_VOICES = frozenset(
    {"alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse", "marin", "cedar"}
)

# Confirmed against `claude --help` (--permission-mode) in this environment on 2026-09-20.
VALID_PERMISSION_MODES = frozenset(
    {"acceptEdits", "auto", "bypassPermissions", "manual", "dontAsk", "plan"}
)

# "center" isn't a corner, but lives in the same AI_BUTLER_VISUALIZER_CORNER
# setting to avoid a second env var for what's really one "where" choice.
VALID_VISUALIZER_CORNERS = frozenset(
    {"center", "top-left", "top-right", "bottom-left", "bottom-right"}
)


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _env_int(source: Mapping[str, str], name: str, default: int) -> int:
    raw = source.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name}='{raw}' は整数として解釈できません。") from exc


def _env_bool(source: Mapping[str, str], name: str, default: bool) -> bool:
    raw = source.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Config:
    openai_api_key: str
    realtime_model: str
    voice: str
    hotkey_combo: str
    mic_mute_cooldown_ms: int
    input_device: Optional[str]
    output_device: Optional[str]
    claude_command: Sequence[str]
    claude_permission_mode: Optional[str]
    claude_extra_args: Sequence[str]
    claude_timeout_sec: int
    visualizer_enabled: bool
    visualizer_corner: str

    @staticmethod
    def load(env: Optional[Mapping[str, str]] = None, *, load_env_file: bool = True) -> "Config":
        if load_env_file and env is None and load_dotenv is not None:
            load_dotenv()
        source: Mapping[str, str] = env if env is not None else os.environ

        api_key = source.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ConfigError(
                "OPENAI_API_KEY が設定されていません。.env か環境変数で指定してください。"
            )

        voice = source.get("AI_BUTLER_VOICE", "shimmer").strip()
        if voice not in VALID_VOICES:
            raise ConfigError(
                f"AI_BUTLER_VOICE='{voice}' は未知のvoiceです。"
                f"指定できる値: {', '.join(sorted(VALID_VOICES))}"
            )

        permission_mode = source.get("CLAUDE_CODE_PERMISSION_MODE", "").strip() or None
        if permission_mode and permission_mode not in VALID_PERMISSION_MODES:
            raise ConfigError(
                f"CLAUDE_CODE_PERMISSION_MODE='{permission_mode}' は未知のモードです。"
                f"指定できる値: {', '.join(sorted(VALID_PERMISSION_MODES))}"
            )

        claude_command = tuple(shlex.split(source.get("CLAUDE_CODE_COMMAND", "claude")))
        if not claude_command:
            raise ConfigError("CLAUDE_CODE_COMMAND が空です。")
        claude_extra_args = tuple(shlex.split(source.get("CLAUDE_CODE_EXTRA_ARGS", "")))

        visualizer_corner = source.get("AI_BUTLER_VISUALIZER_CORNER", "center").strip()
        if visualizer_corner not in VALID_VISUALIZER_CORNERS:
            raise ConfigError(
                f"AI_BUTLER_VISUALIZER_CORNER='{visualizer_corner}' は未知の位置です。"
                f"指定できる値: {', '.join(sorted(VALID_VISUALIZER_CORNERS))}"
            )

        return Config(
            openai_api_key=api_key,
            realtime_model=source.get("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1").strip(),
            voice=voice,
            hotkey_combo=source.get("AI_BUTLER_HOTKEY", "<alt>+<space>").strip(),
            mic_mute_cooldown_ms=_env_int(source, "AI_BUTLER_MIC_COOLDOWN_MS", 600),
            input_device=source.get("AI_BUTLER_INPUT_DEVICE", "").strip() or None,
            output_device=source.get("AI_BUTLER_OUTPUT_DEVICE", "").strip() or None,
            claude_command=claude_command,
            claude_permission_mode=permission_mode,
            claude_extra_args=claude_extra_args,
            claude_timeout_sec=_env_int(source, "CLAUDE_CODE_TIMEOUT_SEC", 1800),
            visualizer_enabled=_env_bool(source, "AI_BUTLER_VISUALIZER", True),
            visualizer_corner=visualizer_corner,
        )
