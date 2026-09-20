"""Tracks whether the microphone should currently be captured."""

from __future__ import annotations

import asyncio
from typing import Optional


class MicGate:
    """Two independent switches must both be "go" for audio to be sent upstream.

    - `listening_enabled`: toggled by the global hotkey (Option+Space).
    - the playback gate: closed the moment デヴィ starts speaking, and kept
      closed for a short cooldown after she finishes, so the mic doesn't pick
      up her own voice coming out of the speaker and re-trigger a turn.
    """

    def __init__(self, cooldown_seconds: float, *, listening_enabled: bool = False) -> None:
        self._cooldown = cooldown_seconds
        self._listening_enabled = listening_enabled
        self._playback_gate_open = True
        self._reopen_handle: Optional[asyncio.TimerHandle] = None

    @property
    def listening_enabled(self) -> bool:
        return self._listening_enabled

    @property
    def playback_gate_open(self) -> bool:
        return self._playback_gate_open

    def set_listening_enabled(self, value: bool) -> None:
        self._listening_enabled = value

    def toggle_listening(self) -> bool:
        self._listening_enabled = not self._listening_enabled
        return self._listening_enabled

    def is_mic_open(self) -> bool:
        return self._listening_enabled and self._playback_gate_open

    def on_playback_started(self) -> None:
        """Call when デヴィ starts speaking (first audio delta of a turn)."""
        self._playback_gate_open = False
        if self._reopen_handle is not None:
            self._reopen_handle.cancel()
            self._reopen_handle = None

    def on_playback_finished(self, loop: asyncio.AbstractEventLoop) -> None:
        """Call when デヴィ's turn finishes speaking; reopens after a cooldown."""
        if self._reopen_handle is not None:
            self._reopen_handle.cancel()
        self._reopen_handle = loop.call_later(self._cooldown, self._reopen)

    def _reopen(self) -> None:
        self._playback_gate_open = True
        self._reopen_handle = None
