import pytest

from ai_butler.config import Config, ConfigError


def test_missing_api_key_raises():
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        Config.load(env={}, load_env_file=False)


def test_defaults():
    config = Config.load(env={"OPENAI_API_KEY": "sk-test"}, load_env_file=False)
    assert config.openai_api_key == "sk-test"
    assert config.realtime_model == "gpt-realtime-2.1"
    assert config.voice == "shimmer"
    assert config.hotkey_combo == "<alt>+<space>"
    assert config.mic_mute_cooldown_ms == 600
    assert config.input_device is None
    assert config.output_device is None
    assert config.claude_command == ("claude",)
    assert config.claude_permission_mode is None
    assert config.claude_extra_args == ()
    assert config.claude_timeout_sec == 1800
    assert config.visualizer_enabled is True
    assert config.visualizer_corner == "center"


def test_invalid_voice_raises():
    with pytest.raises(ConfigError, match="AI_BUTLER_VOICE"):
        Config.load(
            env={"OPENAI_API_KEY": "sk-test", "AI_BUTLER_VOICE": "not-a-voice"},
            load_env_file=False,
        )


def test_invalid_permission_mode_raises():
    with pytest.raises(ConfigError, match="CLAUDE_CODE_PERMISSION_MODE"):
        Config.load(
            env={"OPENAI_API_KEY": "sk-test", "CLAUDE_CODE_PERMISSION_MODE": "yolo"},
            load_env_file=False,
        )


def test_claude_command_and_extra_args_are_shell_split():
    config = Config.load(
        env={
            "OPENAI_API_KEY": "sk-test",
            "CLAUDE_CODE_COMMAND": "/usr/local/bin/claude --bare",
            "CLAUDE_CODE_EXTRA_ARGS": "--add-dir /tmp/foo --add-dir '/tmp/bar baz'",
        },
        load_env_file=False,
    )
    assert config.claude_command == ("/usr/local/bin/claude", "--bare")
    assert config.claude_extra_args == ("--add-dir", "/tmp/foo", "--add-dir", "/tmp/bar baz")


def test_invalid_visualizer_corner_raises():
    with pytest.raises(ConfigError, match="AI_BUTLER_VISUALIZER_CORNER"):
        Config.load(
            env={"OPENAI_API_KEY": "sk-test", "AI_BUTLER_VISUALIZER_CORNER": "middle"},
            load_env_file=False,
        )


def test_visualizer_can_be_disabled_and_repositioned():
    config = Config.load(
        env={
            "OPENAI_API_KEY": "sk-test",
            "AI_BUTLER_VISUALIZER": "0",
            "AI_BUTLER_VISUALIZER_CORNER": "bottom-right",
        },
        load_env_file=False,
    )
    assert config.visualizer_enabled is False
    assert config.visualizer_corner == "bottom-right"


def test_custom_int_and_permission_mode():
    config = Config.load(
        env={
            "OPENAI_API_KEY": "sk-test",
            "AI_BUTLER_MIC_COOLDOWN_MS": "1200",
            "CLAUDE_CODE_TIMEOUT_SEC": "60",
            "CLAUDE_CODE_PERMISSION_MODE": "acceptEdits",
        },
        load_env_file=False,
    )
    assert config.mic_mute_cooldown_ms == 1200
    assert config.claude_timeout_sec == 60
    assert config.claude_permission_mode == "acceptEdits"
