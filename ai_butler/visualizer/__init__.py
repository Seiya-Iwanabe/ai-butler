"""Optional floating desktop widget that visualizes デヴィ's voice activity."""

from __future__ import annotations

import logging

from ..config import Config
from .controller import NullVisualizerController, VisualizerController, VisualizerControllerBase

logger = logging.getLogger(__name__)

__all__ = ["create_visualizer", "VisualizerControllerBase"]


def create_visualizer(config: Config) -> VisualizerControllerBase:
    """Build the real visualizer, or a no-op stand-in.

    Anything can legitimately go wrong here on a machine this was never
    tested on (pywebview not installed, no WebKit framework, a headless
    environment, ...). This is an optional visual extra, not core to デヴィ
    actually working, so any failure here falls back to a no-op rather than
    taking down the voice assistant with it -- hence the broad except.
    """
    if not config.visualizer_enabled:
        logger.info("ビジュアライザーは無効化されています(AI_BUTLER_VISUALIZER=0)")
        return NullVisualizerController()

    try:
        from .window import VisualizerWindow

        window = VisualizerWindow(corner=config.visualizer_corner)
        return VisualizerController(window)
    except Exception:
        logger.warning(
            "デスクトップビジュアライザーを起動できなかったため、無効化して続行します"
            "(pywebviewが未インストール、またはGUI非対応の環境の可能性があります)",
            exc_info=True,
        )
        return NullVisualizerController()
