"""API-first audio downloading for the music bot.

The deployed ArtistBots API currently exposes ``/download`` and ``/direct``.
``/download?type=audio`` returns a redirect to a signed Googlevideo audio URL;
the returned media is normally WebM/Opus, so this module converts it to MP3
locally with FFmpeg before handing the path back to the music bot.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
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
        return link.split("youtu.be/", 1)[1].split("?", 1)[0].split("&", 1)[0]
    return link.rsplit("/", 1)[-1].split("?", 1)[0]


def _is_youtube_bot_check(text: str) -> bool:
    value = (text or "").lower()
    return (
        "sign in to confirm" in value
        or "not a bot" in value
        or "confirm you’re not a bot" in value
        or "confirm you're not a bot" in value
    )


def _convert_to_mp3(source: Path, target: Path) -> bool:
    """Convert an API-returned audio container (usually WebM/Opus) to MP3."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        _LOGGER.error("❌ FFmpeg is not installed; cannot convert API audio to MP3")
        return False

    temporary_target = target.with_suffix(".mp3.tmp")
    try:
        if temporary_target.exists():
            temporary_target.unlink()

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-i", str(source),
            "-vn",
            "-map", "0:a:0",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            "-ar", "48000",
            str(temporary_target),
        ]
        completed = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180,
            check=False,
        )
        if completed.returncode != 0 or not temporary_target.is_file() or temporary_target.stat().st_size <= 0:
            error = (completed.stderr or "unknown ffmpeg error").strip()[-500:]
            _LOGGER.error("❌ FFmpeg conversion failed: %s", error)
            return False

        os.replace(temporary_target, target)
        return target.is_file() and target.stat().st_size > 0
    except (OSError, subprocess.SubprocessError) as exc:
        _LOGGER.error("❌ FFmpeg conversion error: %s", exc)
        return False
    finally:
        try:
            if temporary_target.exists():
                temporary_target.unlink()
        except OSError:
            pass


def install_direct_audio_download(youtube) -> None:
    """Patch the YouTube instance so audio uses the deployed API first."""
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
        source = download_dir / f".{video_id}.api_audio"
        partial_source = download_dir / f".{video_id}.api_audio.part"

        if target.is_file() and target.stat().st_size > 0:
            return str(target)

        timeout_seconds = max(int(getattr(self, "api_stream_timeout", 120)), 30)
        timeout = aiohttp.ClientTimeout(
            total=timeout_seconds,
            connect=15,
            sock_read=timeout_seconds,
        )
        headers = {
            "X-API-Key": self.artistbots_key,
            "Accept": "audio/*,application/json,text/plain,*/*;q=0.8",
        }

        base_url = self.api_url.rstrip("/")
        direct_endpoint = f"{base_url}/direct"
        download_endpoint = f"{base_url}/download"
        download_params = {"url": video_id, "type": "audio", "api_key": self.artistbots_key}
        direct_params = {"url": video_id, "api_key": self.artistbots_key}

        async def save_and_convert(response: aiohttp.ClientResponse) -> Optional[str]:
            """Save response bytes and convert the returned container to MP3."""
            if response.status != 200:
                return None

            with partial_source.open("wb") as output:
                async for chunk in response.content.iter_chunked(256 * 1024):
                    if chunk:
                        output.write(chunk)

            if not partial_source.is_file() or partial_source.stat().st_size <= 0:
                return None

            os.replace(partial_source, source)
            if not _convert_to_mp3(source, target):
                return None

            try:
                source.unlink(missing_ok=True)
            except OSError:
                pass
            return str(target)

        try:
            _LOGGER.info("🎯 [API AUDIO] trying /direct for %s", video_id)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # /direct returns JSON containing the signed media URL. This
                # avoids making the bot depend on browser redirect handling.
                try:
                    async with session.get(
                        direct_endpoint,
                        params=direct_params,
                        headers=headers,
                        allow_redirects=True,
                    ) as response:
                        if response.status == 200:
                            content_type = (response.headers.get("content-type") or "").lower()
                            if "json" in content_type:
                                body = await response.text(errors="ignore")
                                try:
                                    payload = json.loads(body)
                                except json.JSONDecodeError:
                                    payload = None
                                media_url = payload.get("url") if isinstance(payload, dict) else None
                                if media_url:
                                    _LOGGER.info("🔗 [API DIRECT] signed audio URL resolved for %s", video_id)
                                    async with session.get(
                                        media_url,
                                        headers={"Accept": "audio/*,*/*;q=0.8"},
                                        allow_redirects=True,
                                    ) as media_response:
                                        result = await save_and_convert(media_response)
                                        if result:
                                            _LOGGER.info("✅ [API SUCCESS] MP3 ready: %s", result)
                                            return result
                                else:
                                    _LOGGER.warning("⚠️ /direct returned JSON without a media URL for %s", video_id)
                            else:
                                # Be tolerant if a future deployment makes /direct stream media.
                                result = await save_and_convert(response)
                                if result:
                                    _LOGGER.info("✅ [API SUCCESS] MP3 ready: %s", result)
                                    return result
                        else:
                            body = (await response.text(errors="ignore"))[:500]
                            _LOGGER.warning("API /direct returned HTTP %s for %s: %s", response.status, video_id, body)
                            if _is_youtube_bot_check(body):
                                _LOGGER.warning("🛑 API reports a YouTube bot-check for %s; skipping duplicate API retries", video_id)
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    _LOGGER.warning("⚠️ /direct request failed for %s: %s", video_id, exc)

                # Known-compatible endpoint. It follows the API's 302 to the
                # signed Googlevideo URL and then converts WebM/Opus to MP3.
                _LOGGER.info("🎯 [API AUDIO] trying /download for %s", video_id)
                async with session.get(
                    download_endpoint,
                    params=download_params,
                    headers=headers,
                    allow_redirects=True,
                ) as response:
                    if response.status == 200:
                        result = await save_and_convert(response)
                        if result:
                            _LOGGER.info("✅ [API SUCCESS] Downloaded and converted: %s", result)
                            return result
                        _LOGGER.warning("⚠️ API /download returned media but conversion failed for %s", video_id)
                    else:
                        body = (await response.text(errors="ignore"))[:700]
                        _LOGGER.warning(
                            "API /download returned HTTP %s for %s: %s",
                            response.status,
                            video_id,
                            body,
                        )
                        if _is_youtube_bot_check(body):
                            _LOGGER.warning(
                                "🛑 YouTube bot-check came from API for %s; do not repeat the same request",
                                video_id,
                            )

        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            _LOGGER.warning("🌐 API audio request failed for %s: %s", video_id, exc)
        except Exception as exc:
            _LOGGER.exception("❌ Unexpected API audio error for %s: %s", video_id, exc)
        finally:
            for path in (partial_source, source):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

        _LOGGER.error("❌ [API FAILED] Could not download %s via API", video_id)
        return None

    youtube._logger = _LOGGER
    youtube.download_via_api = MethodType(download_via_api, youtube)
    youtube._direct_audio_download_installed = True
