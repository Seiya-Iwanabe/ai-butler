"""Entrypoint: wires mic, speaker, hotkey, the visualizer and the Realtime session together.

Threading model: the desktop visualizer (when active) needs pywebview's
blocking `webview.start()` on the process's real main thread (a macOS/Cocoa
requirement -- see visualizer/window.py). So when it's active, the entire
asyncio pipeline below runs on a background thread instead, and the two
sides are cross-wired to shut down together: closing the widget sets
`shutdown_event`, which the asyncio side watches; the asyncio side exiting
for any other reason closes the widget window. When the visualizer is
disabled/unavailable, this all collapses back to the simple single-thread
`asyncio.run()` on the main thread.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import threading

from .audio_io import MicStream, SpeakerPlayer
from .config import Config, ConfigError
from .hotkey import HotkeyListener
from .mic_gate import MicGate
from .realtime_client import RealtimeSession
from .visualizer import VisualizerControllerBase, create_visualizer

logger = logging.getLogger("ai_butler")


async def _pump_mic(mic_stream: MicStream, session: RealtimeSession) -> None:
    async for frame in mic_stream.frames():
        await session.send_audio(frame)


async def async_main(
    config: Config,
    visualizer: VisualizerControllerBase,
    shutdown_event: threading.Event,
) -> None:
    mic_gate = MicGate(cooldown_seconds=config.mic_mute_cooldown_ms / 1000)
    speaker = SpeakerPlayer(device=config.output_device)
    speaker.__enter__()
    try:
        async def speaker_write(pcm: bytes) -> None:
            await asyncio.to_thread(speaker.write, pcm)

        session = RealtimeSession(config, mic_gate, speaker_write, visualizer)
        await session.connect()

        loop = asyncio.get_running_loop()

        def on_hotkey() -> None:
            enabled = mic_gate.toggle_listening()
            logger.info("音声認識を%sにしました (%s)", "ON" if enabled else "OFF", config.hotkey_combo)

        hotkey = HotkeyListener(config.hotkey_combo, on_hotkey)
        hotkey.start(loop)

        stop_event = asyncio.Event()
        # signal handlers can only be registered from the process's real
        # main thread; when the visualizer owns the main thread, this
        # thread relies on shutdown_event (closing the widget) instead.
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, stop_event.set)
                except NotImplementedError:
                    pass  # not supported on this platform (e.g. Windows)

        try:
            async with MicStream(
                device=config.input_device,
                should_capture=mic_gate.is_mic_open,
                visualizer=visualizer,
            ) as mic_stream:
                mic_task = asyncio.create_task(_pump_mic(mic_stream, session))
                session_task = asyncio.create_task(session.run())
                stop_task = asyncio.create_task(stop_event.wait())
                shutdown_task = asyncio.create_task(asyncio.to_thread(shutdown_event.wait))

                logger.info("デヴィが起動したよ。%s で話しかけてね。", config.hotkey_combo)
                all_tasks = {mic_task, session_task, stop_task, shutdown_task}
                await asyncio.wait(all_tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in all_tasks:
                    task.cancel()
                await asyncio.gather(*all_tasks, return_exceptions=True)
        finally:
            hotkey.stop()
            await session.close()
    finally:
        speaker.__exit__(None, None, None)


def _run_pipeline(config: Config, visualizer: VisualizerControllerBase, shutdown_event: threading.Event) -> None:
    try:
        asyncio.run(async_main(config, visualizer, shutdown_event))
    except KeyboardInterrupt:
        pass
    finally:
        shutdown_event.set()
        visualizer.close_window_if_open()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    try:
        config = Config.load()
    except ConfigError as exc:
        logger.error(str(exc))
        raise SystemExit(1) from None

    visualizer = create_visualizer(config)
    visualizer.start()
    shutdown_event = threading.Event()
    visualizer.on_closed(shutdown_event.set)

    if visualizer.is_active:
        pipeline_thread = threading.Thread(
            target=_run_pipeline,
            args=(config, visualizer, shutdown_event),
            name="ai-butler-pipeline",
            daemon=True,
        )
        pipeline_thread.start()

        # Blocks the main thread until the widget window closes. Note:
        # Ctrl+C may not interrupt this promptly while it's blocked in
        # pywebview's native event loop -- a known limitation of embedding
        # a native GUI loop in Python. Closing the widget, or
        # `claude stop <session-id>` if running in the background, both
        # still work.
        #
        # webview.start() can also raise outright (confirmed in this repo's
        # dev sandbox: WebViewException when no GUI backend -- e.g. no
        # GTK/Qt -- is available at all). The pipeline thread above is
        # already running by this point, so on that failure we fall back to
        # waiting on it headlessly instead of taking デヴィ's voice loop
        # down with the widget.
        gui_started = True
        try:
            visualizer.run_blocking()
        except KeyboardInterrupt:
            pass
        except Exception:
            gui_started = False
            logger.warning(
                "デスクトップビジュアライザーの起動に失敗したため、"
                "ウィジェットなしで続行します",
                exc_info=True,
            )

        if gui_started:
            # run_blocking() returned because the widget closed (or Ctrl+C
            # reached it) -- ask the pipeline to stop and wait briefly.
            shutdown_event.set()
            pipeline_thread.join(timeout=5.0)
        else:
            # No GUI backend at all: the pipeline thread is our whole
            # program now, so wait on it the way the no-visualizer branch
            # below does (indefinitely; Ctrl+C works normally here since
            # we're back in plain Python on the main thread, not stuck in
            # a native GUI loop).
            try:
                pipeline_thread.join()
            except KeyboardInterrupt:
                shutdown_event.set()
                pipeline_thread.join(timeout=5.0)

        visualizer.stop()
    else:
        try:
            _run_pipeline(config, visualizer, shutdown_event)
        finally:
            visualizer.stop()


if __name__ == "__main__":
    main()
