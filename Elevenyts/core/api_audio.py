"""Reliable audio resolution for the remote music API.

The API's fast audio endpoint returns JSON containing a signed YouTube URL.
Keeping the API request and the signed-media request separate avoids treating
the API's 302 response as an empty audio file.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import MethodType
from typing import Optional

import aiohttp


def install_direct_audio_download(youtube) -> None:
    """Make audio downloads use ``/direct`` while preserving video downloads."""

    if getattr(youtube, "_direct_audio_download_installed", False):
        return

    original_download_via_api = youtube.download_via_api

    async def download_via_api(
        self,
        link: str,
        video: bool = False,
    ) -> Optional[str]:
        # Keep the existing binary /download contract for video playback.
        if video:
            return await original_download_via_api(link, video=True)

        video_id = link
        if "v=" in link:
            video_id = link.split("v=", 1)[1].split("&", 1)[0]
        elif "youtu.be/" in link:
            video_id = link.split("youtu.be/", 1)[1].split("?", 1)[0]

        if not video_id or len(video_id) < 3:
            return None

        download_dir = Path("downloads")
        download_dir.mkdir(parents=True, exist_ok=True)
        target = download_dir / f"{video_id}.mp3"
        partial = download_dir / f".{video_id}.mp3.part"

        if target.is_file() and target.stat().st_size > 0:
            return str(target)

        api_endpoint = f"{self.api_url.rstrip('/')}/direct"
        headers = {"X-API-Key": self.artistbots_key}
        timeout = aiohttp.ClientTimeout(total=self.api_stream_timeout)

        try:
            async with aiohttp.ClientSession() as session:
                # This response is JSON, not audio. Do not use /download's 302
                # response as the file body.
                async with session.get(
                    api_endpoint,
                    params={"url": video_id},
                    headers=headers,
                    timeout=timeout,
                ) as response:
                    if response.status != 200:
                        body = (await response.text())[:200]
                        self._logger.error(
                            "Direct audio API returned %s for %s: %s",
                            response.status,
                            video_id,
                            body,
                        )
                        return None
                    payload = await response.json(content_type=None)

                audio_url = payload.get("url") if isinstance(payload, dict) else None
                if not isinstance(audio_url, str) or not audio_url.startswith(("http://", "https://")):
                    self._logger.error("Direct audio API returned no usable URL for %s", video_id)
                    return None

                # Fetch the signed YouTube URL explicitly. The API key must not
                # be forwarded to this third-party URL.
                async with session.get(
                    audio_url,
                    allow_redirects=True,
                    timeout=timeout,
                ) as media_response:
                    if media_response.status != 200:
                        self._logger.error(
                            "Signed audio URL returned %s for %s",
                            media_response.status,
                            video_id,
                        )
                        return None

                    downloaded = 0
                    with partial.open("wb") as output:
                        async for chunk in media_response.content.iter_chunked(64 * 1024):
                            if chunk:
                                output.write(chunk)
                                downloaded += len(chunk)

                if downloaded <= 0 or not partial.is_file() or partial.stat().st_size <= 0:
                    self._logger.error("Signed audio response was empty for %s", video_id)
                    return None

                os.replace(partial, target)
                self._logger.info(
                    "Direct audio downloaded for %s (%d bytes)",
                    video_id,
                    downloaded,
                )
                return str(target)

        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError) as exc:
            self._logger.error("Direct audio download failed for %s: %s", video_id, exc)
            return None
        finally:
            # Never leave a partial file that can be mistaken for a valid cache.
            try:
                if partial.exists():
                    partial.unlink()
            except OSError:
                pass

    # The original YouTube class does not expose a logger, so attach the
    # module logger through the instance without changing the obfuscated file.
    import logging

    youtube._logger = logging.getLogger(__name__)
    youtube.download_via_api = MethodType(download_via_api, youtube)
    youtube._direct_audio_download_installed = True