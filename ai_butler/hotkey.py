"""Global hotkey listener (default: Option+Space) bridged into asyncio.

Custom Quartz.CGEventTapCreate-based implementation (macOS only) rather
than pynput.keyboard.GlobalHotKeys.

Why not pynput: confirmed by reading pynput's own source
(pynput/_util/darwin.py, pynput/keyboard/_darwin.py) that its macOS
Listener resolves keycodes via TISCopyCurrentKeyboardInputSource() and
other Carbon Text Services Manager (TSM) calls, on its own internal
listener thread, every time it starts (`Listener._run()` always enters
`keycode_context()`, regardless of which thread called `.start()`). TSM
enforces a hard "must be called from the main thread" assertion once a
real Cocoa app (NSApplication) exists on the process's main thread --
which ai_butler's pywebview-based visualizer creates. This combination
was confirmed (via live user testing on macOS) to crash the whole process
with a TSM assertion as soon as both the visualizer and the pynput hotkey
listener were active together. See docs/DESIGN.md.

This implementation only needs a fixed physical key (by its
layout-independent macOS virtual keycode -- see hotkey_combo.py) plus a
modifier-flag bitmask, so it never needs to translate a keycode to a
character and never touches TSM, sidestepping the conflict entirely
rather than working around thread scheduling.

On macOS this requires granting the terminal/app running ai-butler
Accessibility permission (System Settings -> Privacy & Security ->
Accessibility), the same requirement pynput had -- CGEventTapCreate
returns None without it, which is treated as a (logged) soft failure.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

import Quartz

from .hotkey_combo import RELEVANT_FLAGS_MASK, parse_combo

logger = logging.getLogger(__name__)

# How long each CFRunLoopRunInMode call blocks for, in seconds, before
# re-checking whether stop() was called. Matches the interval pynput's own
# ListenerMixin uses for this same pattern.
_RUN_LOOP_POLL_INTERVAL_SEC = 1.0


class HotkeyListener:
    def __init__(self, combo: str, on_trigger: Callable[[], None]) -> None:
        self._modifier_mask, self._keycode = parse_combo(combo)
        self._combo_label = combo
        self._on_trigger = on_trigger
        self._loop = None
        self._thread: Optional[threading.Thread] = None
        self._run_loop = None
        self._running = False

    def start(self, loop) -> None:
        self._loop = loop
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="ai-butler-hotkey", daemon=True
        )
        self._thread.start()
        logger.info("グローバルホットキー %s を監視開始しました", self._combo_label)

    def stop(self) -> None:
        self._running = False
        run_loop = self._run_loop
        if run_loop is not None:
            Quartz.CFRunLoopStop(run_loop)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        event_mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            event_mask,
            self._handle_event,
            None,
        )
        if tap is None:
            logger.warning(
                "グローバルホットキーを監視できませんでした。システム設定 → "
                "プライバシーとセキュリティ → アクセシビリティ で、このアプリ"
                "(ターミナル)を許可してください。ホットキー無しで続行します。"
            )
            return

        run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        self._run_loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(
            self._run_loop, run_loop_source, Quartz.kCFRunLoopDefaultMode
        )
        Quartz.CGEventTapEnable(tap, True)

        try:
            while self._running:
                Quartz.CFRunLoopRunInMode(
                    Quartz.kCFRunLoopDefaultMode, _RUN_LOOP_POLL_INTERVAL_SEC, False
                )
        finally:
            self._run_loop = None

    def _handle_event(self, proxy, event_type, event, refcon):
        if event_type == Quartz.kCGEventKeyDown:
            keycode = Quartz.CGEventGetIntegerValueField(
                event, Quartz.kCGKeyboardEventKeycode
            )
            flags = Quartz.CGEventGetFlags(event) & RELEVANT_FLAGS_MASK
            if keycode == self._keycode and flags == self._modifier_mask:
                loop = self._loop
                if loop is not None:
                    loop.call_soon_threadsafe(self._on_trigger)
        # Listen-only tap: no event mutation, nothing to return.
