"""WebSocket orchestration for the OpenAI Realtime API (gpt-realtime-2.1)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Awaitable, Callable, Optional

import websockets
from websockets.asyncio.client import ClientConnection

from . import realtime_protocol as proto
from .claude_bridge import ClaudeCodeError, run_claude_code
from .config import Config
from .mic_gate import MicGate
from .persona import PERSONA_INSTRUCTIONS

logger = logging.getLogger(__name__)

REALTIME_URL = "wss://api.openai.com/v1/realtime"

# Trimmed before being fed back into the conversation as the function's
# result, to keep token usage (and デヴィ's spoken summary) under control.
MAX_TOOL_OUTPUT_CHARS = 4000


class RealtimeSession:
    def __init__(
        self,
        config: Config,
        mic_gate: MicGate,
        speaker_write: Callable[[bytes], Awaitable[None]],
    ) -> None:
        self._config = config
        self._mic_gate = mic_gate
        self._speaker_write = speaker_write
        self._ws: Optional[ClientConnection] = None
        self._speaking = False

    async def connect(self) -> None:
        url = f"{REALTIME_URL}?model={self._config.realtime_model}"
        headers = {"Authorization": f"Bearer {self._config.openai_api_key}"}
        self._ws = await websockets.connect(url, additional_headers=headers, max_size=None)
        await self._send(
            proto.session_update_event(
                instructions=PERSONA_INSTRUCTIONS,
                voice=self._config.voice,
                model=self._config.realtime_model,
            )
        )
        logger.info(
            "Realtime APIに接続しました (model=%s, voice=%s)",
            self._config.realtime_model,
            self._config.voice,
        )

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _send(self, event: dict) -> None:
        if self._ws is None:
            raise RuntimeError("RealtimeSession is not connected")
        await self._ws.send(proto.dumps(event))

    async def send_audio(self, pcm_bytes: bytes) -> None:
        b64 = base64.b64encode(pcm_bytes).decode("ascii")
        await self._send(proto.input_audio_append_event(b64))

    async def run(self) -> None:
        if self._ws is None:
            raise RuntimeError("RealtimeSession is not connected")
        async for raw in self._ws:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("JSONとして読めないイベントを受信しました")
                continue
            await self._handle_event(event)

    async def _handle_event(self, event: dict) -> None:
        etype = event.get("type")

        if etype == "response.output_audio.delta":
            if not self._speaking:
                self._speaking = True
                self._mic_gate.on_playback_started()
            delta_b64 = event.get("delta", "")
            if delta_b64:
                await self._speaker_write(base64.b64decode(delta_b64))

        elif etype == "response.output_audio.done":
            self._speaking = False
            self._mic_gate.on_playback_finished(asyncio.get_running_loop())

        elif etype == "response.function_call_arguments.done":
            call_id = event.get("call_id")
            name = event.get("name")
            arguments_raw = event.get("arguments", "{}")
            if name == proto.RUN_CLAUDE_CODE_TOOL_NAME and call_id:
                asyncio.create_task(self._dispatch_claude_code(call_id, arguments_raw))

        elif etype == "error":
            logger.error("Realtime APIエラー: %s", event.get("error"))

    async def _dispatch_claude_code(self, call_id: str, arguments_raw: str) -> None:
        try:
            arguments = json.loads(arguments_raw)
        except json.JSONDecodeError:
            arguments = {}
        task = str(arguments.get("task", "")).strip()

        if not task:
            await self._reply_tool_result(
                call_id, "タスクの内容が空だったので、もう一度お願いしたいと伝えて。"
            )
            return

        try:
            result = await run_claude_code(
                task,
                claude_command=self._config.claude_command,
                permission_mode=self._config.claude_permission_mode,
                extra_args=self._config.claude_extra_args,
                timeout_sec=self._config.claude_timeout_sec,
            )
        except ClaudeCodeError as exc:
            logger.exception("Claude Codeの実行に失敗しました")
            await self._reply_tool_result(call_id, f"Claude Codeの実行に失敗した: {exc}")
            return

        truncated = result[:MAX_TOOL_OUTPUT_CHARS]
        if len(result) > MAX_TOOL_OUTPUT_CHARS:
            truncated += "\n...(以下省略)"
        await self._reply_tool_result(call_id, truncated)

    async def _reply_tool_result(self, call_id: str, output: str) -> None:
        await self._send(proto.function_call_output_event(call_id, output))
        await self._send(proto.response_create_event())
