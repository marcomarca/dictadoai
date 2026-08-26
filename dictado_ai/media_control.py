from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from .config import Settings
from .hotkeys import send_media_play_pause_key

logger = logging.getLogger(__name__)


@dataclass
class PausedMediaTarget:
    backend: str
    target_id: str
    source: str
    title: str | None = None
    extra: dict = field(default_factory=dict)


class MediaManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._last_error = ""

    def stop(self) -> None:
        pass

    def pause_all(self) -> list[PausedMediaTarget]:
        targets: list[PausedMediaTarget] = []
        logger.info("MediaManager: pause_all start")

        targets.extend(self._run_sync(self._pause_winrt_sessions()) or [])

        if self.settings.app.media_key_fallback_enabled:
            targets.extend(self._run_sync(self._pause_with_media_key_if_needed()) or [])
        else:
            logger.info("MediaManager: media_key fallback skipped reason='disabled'")

        logger.info("MediaManager: pause_all complete targets=%s", len(targets))
        return targets

    def resume_all(self, targets: list[PausedMediaTarget]) -> bool:
        if not targets:
            logger.info("MediaManager: resume_all skipped targets=0")
            return False

        logger.info("MediaManager: resume_all targets=%s", len(targets))
        resumed_any = False

        winrt_targets = [target for target in targets if target.backend == "winrt"]
        if winrt_targets:
            resumed_any = bool(self._run_sync(self._resume_winrt_sessions(winrt_targets))) or resumed_any

        if any(target.backend == "media_key" for target in targets):
            if send_media_play_pause_key():
                resumed_any = True
                logger.info("MediaManager: media_key resume sent")
            else:
                logger.warning("MediaManager: media_key resume failed")

        return resumed_any

    def _run_sync(self, coro):
        try:
            return asyncio.run(coro)
        except Exception as exc:
            self._last_error = f"Async error: {exc}"
            logger.error("MediaManager: async task failed", exc_info=True)
            return None

    async def _get_all_sessions(self):
        try:
            from winrt.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as SessionManager,
            )

            manager = await SessionManager.request_async()
            sessions = list(manager.get_sessions())
            logger.debug("MediaManager: found winrt sessions=%s", len(sessions))
            return sessions
        except Exception as exc:
            self._last_error = f"Manager error: {exc}"
            logger.error("MediaManager: error getting winrt sessions", exc_info=True)
            return []

    async def _pause_winrt_sessions(self) -> list[PausedMediaTarget]:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
        )

        targets: list[PausedMediaTarget] = []
        sessions = await self._get_all_sessions()
        for session in sessions:
            try:
                source = session.source_app_user_model_id
                info = session.get_playback_info()
                status = info.playback_status
                logger.info("MediaManager: winrt session source=%r status=%s", source, status)
                if status != PlaybackStatus.PLAYING:
                    continue
                success = await session.try_pause_async()
                if success:
                    title = await self._get_session_title(session)
                    targets.append(
                        PausedMediaTarget(
                            backend="winrt",
                            target_id=source,
                            source=source,
                            title=title,
                        )
                    )
                    logger.info("MediaManager: winrt paused source=%r title=%r", source, title)
                else:
                    logger.warning("MediaManager: winrt pause declined source=%r", source)
            except Exception as exc:
                logger.warning("MediaManager: winrt pause error: %s", exc, exc_info=True)
        return targets

    async def _resume_winrt_sessions(self, targets: list[PausedMediaTarget]) -> bool:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
        )

        target_ids = {target.target_id for target in targets}
        sessions = await self._get_all_sessions()
        resumed_any = False
        for session in sessions:
            try:
                source = session.source_app_user_model_id
                if source not in target_ids:
                    continue
                status = session.get_playback_info().playback_status
                if status == PlaybackStatus.PAUSED:
                    success = await session.try_play_async()
                    resumed_any = bool(success) or resumed_any
                    logger.info("MediaManager: winrt resume source=%r success=%s", source, success)
                else:
                    logger.info("MediaManager: winrt resume skipped source=%r status=%s", source, status)
            except Exception as exc:
                logger.warning("MediaManager: winrt resume error: %s", exc, exc_info=True)
        return resumed_any

    async def _pause_with_media_key_if_needed(self) -> list[PausedMediaTarget]:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
        )

        sessions = await self._get_all_sessions()
        before = {}
        for session in sessions:
            try:
                source = session.source_app_user_model_id
                if session.get_playback_info().playback_status == PlaybackStatus.PLAYING:
                    before[source] = session
            except Exception:
                continue

        if not before:
            logger.info("MediaManager: media_key fallback skipped reason='no playing sessions'")
            return []

        if not send_media_play_pause_key():
            logger.warning("MediaManager: media_key fallback failed reason='sendinput failed'")
            return []

        time.sleep(0.2)
        sessions_after = await self._get_all_sessions()
        changed: list[PausedMediaTarget] = []
        for session in sessions_after:
            try:
                source = session.source_app_user_model_id
                if source not in before:
                    continue
                status = session.get_playback_info().playback_status
                if status == PlaybackStatus.PAUSED:
                    changed.append(
                        PausedMediaTarget(
                            backend="media_key",
                            target_id=source,
                            source=source,
                            extra={"reason": "winrt_playing_session_paused_after_media_key"},
                        )
                    )
            except Exception:
                continue

        if changed:
            logger.info("MediaManager: media_key fallback paused targets=%s", len(changed))
        else:
            logger.warning("MediaManager: media_key fallback no sessions changed")
        return changed

    async def _get_session_title(self, session) -> str | None:
        try:
            properties = await session.try_get_media_properties_async()
            return getattr(properties, "title", None) or None
        except Exception:
            return None
