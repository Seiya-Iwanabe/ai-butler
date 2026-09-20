"""Entrypoint: wires mic, speaker, hotkey and the Realtime session together."""

from __future__ import annotations

import asyncio
import logging
import signal

from .audio_io import MicStream, SpeakerPlayer
from .config import Config, ConfigError
from .hotkey import HotkeyListener
from .mic_gate import MicGate
from .realtime_client import RealtimeSession

logger = logging.getLogger("ai_butler")


async def _pump_mic(mic_stream: MicStream, session: RealtimeSession) -> None:
    async for frame in mic_stream.frames():
        await session.send_audio(frame)


async def async_main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    try:
        config = Config.load()
    except ConfigError as exc:
        logger.error(str(exc))
        raise SystemExit(1) from None

    mic_gate = MicGate(cooldown_seconds=config.mic_mute_cooldown_ms / 1000)
    speaker = SpeakerPlayer(device=config.output_device)
    speaker.__enter__()
    try:
        async def speaker_write(pcm: bytes) -> None:
            await asyncio.to_thread(speaker.write, pcm)

        session = RealtimeSession(config, mic_gate, speaker_write)
        await session.connect()

        loop = asyncio.get_running_loop()

        def on_hotkey() -> None:
            enabled = mic_gate.toggle_listening()
            logger.info("音声認識を%sにしました (%s)", "ON" if enabled else "OFF", config.hotkey_combo)

        hotkey = HotkeyListener(config.hotkey_combo, on_hotkey)
        hotkey.start(loop)

        stop_event = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                pass  # not supported on this platform (e.g. Windows)

        try:
            async with MicStream(
                device=config.input_device, should_capture=mic_gate.is_mic_open
            ) as mic_stream:
                mic_task = asyncio.create_task(_pump_mic(mic_stream, session))
                session_task = asyncio.create_task(session.run())
                stop_task = asyncio.create_task(stop_event.wait())

                logger.info("デヴィが起動したよ。%s で話しかけてね。", config.hotkey_combo)
                await asyncio.wait(
                    {mic_task, session_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in (mic_task, session_task, stop_task):
                    task.cancel()
                await asyncio.gather(mic_task, session_task, stop_task, return_exceptions=True)
        finally:
            hotkey.stop()
            await session.close()
    finally:
        speaker.__exit__(None, None, None)


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
