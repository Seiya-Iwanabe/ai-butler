from pathlib import Path

import pytest

from ai_butler.claude_bridge import ClaudeCodeError, build_command, run_claude_code

FIXTURES = Path(__file__).parent / "fixtures"


def test_build_command_basic():
    cmd = build_command(
        "テストして", claude_command=["claude"], permission_mode=None, extra_args=[]
    )
    assert cmd == ["claude", "-p", "テストして", "--output-format", "text"]


def test_build_command_with_permission_mode_and_extra_args():
    cmd = build_command(
        "テストして",
        claude_command=["claude"],
        permission_mode="acceptEdits",
        extra_args=["--add-dir", "/tmp/x"],
    )
    assert cmd == [
        "claude",
        "-p",
        "テストして",
        "--output-format",
        "text",
        "--permission-mode",
        "acceptEdits",
        "--add-dir",
        "/tmp/x",
    ]


@pytest.mark.asyncio
async def test_run_claude_code_returns_stdout_on_success():
    result = await run_claude_code(
        "洗濯物をたたんで",
        claude_command=[str(FIXTURES / "fake_claude_ok.sh")],
        permission_mode=None,
        extra_args=[],
        timeout_sec=5,
    )
    assert result == "done: 洗濯物をたたんで"


@pytest.mark.asyncio
async def test_run_claude_code_raises_on_nonzero_exit():
    with pytest.raises(ClaudeCodeError) as exc_info:
        await run_claude_code(
            "壊れるタスク",
            claude_command=[str(FIXTURES / "fake_claude_fail.sh")],
            permission_mode=None,
            extra_args=[],
            timeout_sec=5,
        )
    assert "boom" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_claude_code_raises_on_timeout():
    with pytest.raises(ClaudeCodeError) as exc_info:
        await run_claude_code(
            "終わらないタスク",
            claude_command=[str(FIXTURES / "fake_claude_hang.sh")],
            permission_mode=None,
            extra_args=[],
            timeout_sec=1,
        )
    assert "タイムアウト" in str(exc_info.value)
