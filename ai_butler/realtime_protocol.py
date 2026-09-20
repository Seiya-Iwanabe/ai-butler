"""Pure builders for OpenAI Realtime API client events.

No network or I/O here on purpose: every function just returns a plain dict,
so the wire format can be verified with unit tests instead of a live call.

The event/field shapes below were confirmed on 2026-09-20 against the
generated types in openai/openai-python (src/openai/types/realtime/), which
mirrors the server's OpenAPI spec, since the public docs sites were not
reachable from this environment. See docs/DESIGN.md for details and sources.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

RUN_CLAUDE_CODE_TOOL_NAME = "run_claude_code"

# gpt-realtime-2.1 only supports 24kHz mono PCM16 for `audio/pcm`.
AUDIO_FORMAT: Dict[str, Any] = {"type": "audio/pcm", "rate": 24000}

DEFAULT_TURN_DETECTION: Dict[str, Any] = {
    "type": "semantic_vad",
    "eagerness": "auto",
    "create_response": True,
    "interrupt_response": True,
}


def run_claude_code_tool_schema() -> Dict[str, Any]:
    """Function-tool definition handed to the model in `session.update`."""
    return {
        "type": "function",
        "name": RUN_CLAUDE_CODE_TOOL_NAME,
        "description": (
            "せいちゃんが依頼したコーディング/開発タスクを、せいちゃんのマシンで動いている"
            "Claude Code(コマンドラインのコーディングAI)にそのまま丸ごと渡して実行させる。"
            "コードを書いたり実行したりする作業は絶対に自分でやらず、必ずこの関数を呼んで"
            "Claude Codeに任せること。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Claude Codeにそのまま渡す、依頼内容の自然な文章(日本語)。",
                }
            },
            "required": ["task"],
            "additionalProperties": False,
        },
    }


def session_update_event(
    *,
    instructions: str,
    voice: str,
    model: str,
    turn_detection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "model": model,
            "instructions": instructions,
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": dict(AUDIO_FORMAT),
                    "turn_detection": turn_detection or dict(DEFAULT_TURN_DETECTION),
                },
                "output": {
                    "format": dict(AUDIO_FORMAT),
                    "voice": voice,
                },
            },
            "tools": [run_claude_code_tool_schema()],
            "tool_choice": "auto",
        },
    }


def input_audio_append_event(audio_b64: str) -> Dict[str, Any]:
    return {"type": "input_audio_buffer.append", "audio": audio_b64}


def function_call_output_event(call_id: str, output: str) -> Dict[str, Any]:
    return {
        "type": "conversation.item.create",
        "item": {
            "type": "function_call_output",
            "call_id": call_id,
            "output": output,
        },
    }


def system_message_event(text: str) -> Dict[str, Any]:
    return {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "system",
            "content": [{"type": "input_text", "text": text}],
        },
    }


def response_create_event() -> Dict[str, Any]:
    return {"type": "response.create"}


def dumps(event: Dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False)
