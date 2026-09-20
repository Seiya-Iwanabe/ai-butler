"""Hands a task off to the user's own Claude Code CLI and returns its final output."""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)


class ClaudeCodeError(RuntimeError):
    """Raised when the Claude Code CLI invocation fails or times out."""


def build_command(
    task: str,
    *,
    claude_command: Sequence[str],
    permission_mode: Optional[str],
    extra_args: Sequence[str],
) -> List[str]:
    """Build the argv for a non-interactive (`-p`/print mode) Claude Code call.

    Flags confirmed against `claude --help` in this environment on 2026-09-20:
    `-p/--print`, `--output-format text|json|stream-json`,
    `--permission-mode <acceptEdits|auto|bypassPermissions|manual|dontAsk|plan>`.
    """
    cmd = [*claude_command, "-p", task, "--output-format", "text"]
    if permission_mode:
        cmd += ["--permission-mode", permission_mode]
    cmd += list(extra_args)
    return cmd


async def run_claude_code(
    task: str,
    *,
    claude_command: Sequence[str],
    permission_mode: Optional[str],
    extra_args: Sequence[str],
    timeout_sec: int,
) -> str:
    """Run Claude Code headlessly and return its final stdout text.

    Note: without `permission_mode` set, tool calls that would normally prompt
    for approval have no TTY to prompt on, so Claude Code will typically deny
    them rather than hang. To let it work fully unattended, set
    CLAUDE_CODE_PERMISSION_MODE (e.g. to `bypassPermissions` or `acceptEdits`)
    -- understand that this removes a safety net before doing so.
    """
    cmd = build_command(
        task,
        claude_command=claude_command,
        permission_mode=permission_mode,
        extra_args=extra_args,
    )
    logger.info("Claude Codeにタスクを渡します: %s", task)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise ClaudeCodeError(f"{timeout_sec}秒でタイムアウトしました") from None

    stdout_text = stdout.decode("utf-8", errors="replace").strip()
    stderr_text = stderr.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        raise ClaudeCodeError(
            stderr_text or f"claude がエラー終了しました (exit code {proc.returncode})"
        )

    return stdout_text or "(Claude Codeから出力はありませんでした)"
