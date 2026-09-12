"""Reliable API-first audio downloading for the music bot.

Audio is fetched through the API's /stream endpoint.  The API resolves and
proxies the signed YouTube media URL itself, so the bot does not make a second
request to YouTube from a different Heroku egress IP.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from types import MethodType
from typing import Optional

import aiohttp


_LOGGER = logging.getLogger("Elevenyts.core.api_audio")


def _video_id(link: str) -> str:
    link = (link or "").strip()
    if "v=" in link:
        return link.split("v=", 1)[1].split("&", 1)[0]
    if "youtu.be/" in link:
        return link.split("youtu.be/", 1)[1].split("?", 1)[0]
    return link.rsplit("/", 1)[-1].split("?", 1)[0]


def install_direct_audio_download(youtube) -> None:
    """Patch the YouTube instance so audio always uses the API stream path."""
    if getattr(youtube, "_direct_audio_download_installed", False):
        return

    original_download_via_api = youtube.download_via_api

    async def download_via_api(self, link: str, video: bool = False) -> Optional[str]:
        # Keep the existing video API implementation untouched.
        if video:
            return await original_download_via_api(link, video=True)

        video_id = _video_id(link)
        if not video_id or len(video_id) < 3:
            _LOGGER.warning("Invalid video id for API download: %r", video_id)
            return None

        if not self.enable_api or not self.api_url or not self.artistbots_key:
            return None

        download_dir = Path("downloads")
        download_dir.mkdir(parents=True, exist_ok=True)
        target = download_dir / f"{video_id}.mp3"
        partial = download_dir / f".{video_id}.mp3.part"

        if target.is_file() and target.stat().st_size > 0:
            return str(target)

        endpoint = f"{self.api_url.rstrip('/')}/stream"
        timeout_seconds = max(int(getattr(self, "api_stream_timeout", 120)), 30)
        timeout = aiohttp.ClientTimeout(
            total=timeout_seconds,
            connect=15,
            sock_read=timeout_seconds,
        )
        headers = {
            "X-API-Key": self.artistbots_key,
            "Accept": "audio/*,*/*;q=0.8",
        }
        params = {"url": video_id}

        # A transient YouTube/API failure should not immediately trigger the
        # slow cookie fallback.  Retry the API itself first.
        for attempt in range(1, 4):
            try:
                _LOGGER.info(
                    "🎯 [API AUDIO] /stream attempt %d/3 for %s",
                    attempt,
                    video_id,
                )
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(
                        endpoint,
                        params=params,
                        headers=headers,
                        allow_redirects=True,
                    ) as response:
                        if response.status != 200:
                            body = (await response.text(errors="ignore"))[:300]
                            _LOGGER.warning(
                                "API /stream returned HTTP %s for %s: %s",
                                response.status,
                                video_id,
                                body,
                            )
                        else:
                            downloaded = 0
                            with partial.open("wb") as output:
                                async for chunk in response.content.iter_chunked(256 * 1024):
                                    if chunk:
                                        output.write(chunk)
                                        downloaded += len(chunk)

                            if downloaded > 0 and partial.is_file():
                                os.replace(partial, target)
                                _LOGGER.info(
                                    "Direct audio downloaded for %s (%d bytes)",
                                    video_id,
                                    downloaded,
                                )
                                return str(target)

                            _LOGGER.warning("API /stream returned an empty body for %s", video_id)

            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                _LOGGER.warning(
                    "API /stream attempt %d failed for %s: %s",
                    attempt,
                    video_id,
                    exc,
                )
            except Exception as exc:
                _LOGGER.exception(
                    "Unexpected API audio error for %s: %s",
                    video_id,
                    exc,
                )

            # Short backoff prevents three immediate identical requests while
            # still keeping playback fast.
            if attempt < 3:
                await asyncio.sleep(0.75 * attempt)

        try:
            if partial.exists():
                partial.unlink()
        except OSError:
            pass

        _LOGGER.error("API audio failed after 3 attempts for %s", video_id)
        return None

    youtube._logger = _LOGGER
    youtube.download_via_api = MethodType(download_via_api, youtube)
    youtube._direct_audio_download_installed = True
