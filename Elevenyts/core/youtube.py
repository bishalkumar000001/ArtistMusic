# ==========================================================
# Copyright (c) 2026 VelocityBots
# All Rights Reserved.
#
# Project      : VelocityBots ꭙ Music Telegram Bot
# Powered By   : Artist
# Type         : API Based Telegram Music Bot
#
# Bot          : @ArtistApibot
# Channel      : https://t.me/artistbots
# GitHub       : https://github.com/elevenyts
#
# Unauthorized copying, modification, or redistribution
# of this source code without permission is prohibited.
# ==========================================================

import os
import re
import glob
import time
import yt_dlp
import random
import asyncio
import aiohttp
from dataclasses import replace
from pathlib import Path
from typing import Optional, Union

from pyrogram import enums, types
from py_yt import Playlist, VideosSearch
from Elevenyts import config, logger
from Elevenyts.helpers import Track, utils


class YouTube:
    def __init__(self):
        """Initialize YouTube handler with configuration and caching."""
        self.base = "https://www.youtube.com/watch?v="
        self.cookies = []
        self.checked = False
        self.warned = False

        # Get API configuration from config
        self.api_url = config.ARTISTBOTS_API_URL
        self.artistbots_key = config.ARTISTBOTS_KEY
        self.enable_api = config.ENABLE_API
        self.enable_cookies_fallback = config.ENABLE_COOKIES_FALLBACK
        self.api_timeout = config.API_TIMEOUT
        self.api_stream_timeout = config.API_STREAM_TIMEOUT

        # Regular expression to match YouTube URLs
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|live/|embed/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )

        # Cache search results (10 minute TTL)
        self.search_cache = {}
        self._download_semaphore = asyncio.Semaphore(5)
        self._max_video_height = config.VIDEO_MAX_HEIGHT

        # Log configuration
        logger.info("=" * 50)
        logger.info("📹 YouTube Handler Initialized")
        logger.info(f"🎵 API Priority: {'ENABLED' if self.enable_api else 'DISABLED'}")
        if self.enable_api:
            logger.info(f"🔗 API URL: {self.api_url}")
            if self.artistbots_key:
                masked_key = self.artistbots_key[:8] + "..." if len(self.artistbots_key) > 8 else "***"
                logger.info(f"🔑 API Key: {masked_key}")
            else:
                logger.warning("⚠️ No API Key configured!")
        logger.info(f"🍪 Cookies Fallback: {'ENABLED' if self.enable_cookies_fallback else 'DISABLED'}")
        logger.info("=" * 50)

    def _locate_download_file(self, video_id: str, video: bool = False) -> Optional[str]:
        """Locate any completed download file for a video id."""
        pattern = f"downloads/{video_id}*"
        candidates = sorted([
            path for path in glob.glob(pattern)
            if not path.endswith((".part", ".ytdl", ".info.json", ".temp"))
        ])

        video_exts = {".mp4", ".mkv", ".webm", ".mov"}
        audio_exts = {".m4a", ".webm", ".opus", ".mp3", ".ogg", ".wav", ".flac"}

        if video:
            for path in candidates:
                if os.path.isdir(path):
                    continue
                if Path(path).suffix.lower() in video_exts:
                    return path
        else:
            for path in candidates:
                if os.path.isdir(path):
                    continue
                if Path(path).suffix.lower() in audio_exts:
                    return path

        for path in candidates:
            if os.path.isdir(path):
                continue
            return path
        return None

    def get_cookies(self):
        """Get random cookie file from cookies directory."""
        if not self.checked:
            cookies_dir = "Elevenyts/cookies"
            if os.path.exists(cookies_dir):
                for file in os.listdir(cookies_dir):
                    if file.endswith(".txt"):
                        self.cookies.append(file)
            self.checked = True
        
        if not self.cookies:
            if not self.warned:
                self.warned = True
                logger.warning("🍪 Cookies are missing; downloads might fail.")
            return None
        
        cookie_file = f"Elevenyts/cookies/{random.choice(self.cookies)}"
        logger.debug(f"Using cookie file: {cookie_file}")
        return cookie_file

    async def save_cookies(self, urls: list[str]) -> None:
        """Save cookies from URLs to files."""
        logger.info("🍪 Saving cookies from urls...")
        saved_count = 0
        
        # Create cookies directory if not exists
        cookies_dir = Path("Elevenyts/cookies")
        cookies_dir.mkdir(parents=True, exist_ok=True)
        
        for url in urls:
            try:
                # Generate unique filename
                path = cookies_dir / f"cookie{random.randint(10000, 99999)}.txt"
                
                # Convert to raw URL if needed
                if "pastebin.com" in url:
                    link = url.replace("pastebin.com", "pastebin.com/raw")
                elif "batbin.me" in url:
                    link = url.replace("batbin.me", "batbin.me/raw")
                else:
                    link = url
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(link, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status != 200:
                            logger.error(f"❌ Cookie download failed: HTTP {resp.status} from {url}")
                            continue
                        
                        content = await resp.read()
                        if not content or len(content) < 50:
                            logger.error(f"❌ Cookie file empty or invalid from {url}")
                            continue
                        
                        # Save cookie file
                        with open(path, "wb") as fw:
                            fw.write(content)
                        
                        if path.exists() and path.stat().st_size > 0:
                            saved_count += 1
                            cookie_filename = path.name
                            if cookie_filename not in self.cookies:
                                self.cookies.append(cookie_filename)
                            logger.info(f"✅ Saved: {cookie_filename} ({len(content)} bytes)")
                            
            except asyncio.TimeoutError:
                logger.error(f"❌ Cookie download timeout from {url}")
            except Exception as e:
                logger.error(f"❌ Cookie download error from {url}: {e}")
        
        self.checked = True
        
        if saved_count > 0:
            logger.info(f"✅ Cookies saved successfully! ({saved_count} file(s))")
        else:
            logger.error("❌ No cookies saved! Check COOKIE_URL in .env.")

    async def download_via_api(self, link: str, video: bool = False) -> Optional[str]:
        """Download media directly from the ArtistBots streaming API.

        The API performs yt-dlp extraction server-side and returns the finished
        media file in the same HTTP response, avoiding the slower JSON metadata
        + /files second-request flow.
        """
        if not self.enable_api:
            logger.debug("API is disabled in config")
            return None
        if not self.api_url:
            logger.debug("ARTISTBOTS_API_URL not configured")
            return None

        if "v=" in link:
            video_id = link.split("v=")[-1].split("&")[0]
        elif "youtu.be" in link:
            video_id = link.split("/")[-1].split("?")[0]
        else:
            video_id = link

        if not video_id or len(video_id) < 3:
            logger.debug(f"Invalid video ID: {video_id}")
            return None

        download_dir = "downloads"
        os.makedirs(download_dir, exist_ok=True)
        file_ext = ".mp4" if video else ".mp3"
        file_path = os.path.join(download_dir, f"{video_id}{file_ext}")
        part_path = file_path + ".part"

        if os.path.exists(file_path) and os.path.getsize(file_path) > 1024:
            logger.debug(f"File already exists: {file_path}")
            return file_path
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        if os.path.exists(part_path):
            try:
                os.remove(part_path)
            except OSError:
                pass

        try:
            download_type = "video" if video else "audio"
            api_started = time.monotonic()
            logger.info(f"🚀 [API DIRECT] Downloading {download_type} for {video_id}")
            endpoint = "/video-stream" if video else "/stream"
            api_endpoint = f"{self.api_url.rstrip('/')}{endpoint}"
            headers = {
                "X-API-Key": self.artistbots_key,
                "Accept": "audio/mpeg,video/mp4,application/octet-stream,*/*",
            }

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.api_stream_timeout)
            ) as session:
                async with session.get(
                    api_endpoint,
                    params={"url": video_id},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.api_stream_timeout),
                ) as response:
                    headers_received = time.monotonic()
                    header_wait = headers_received - api_started
                    logger.info(f"⏱️ [API TIMING] Response headers received for {video_id} after {header_wait:.2f}s (HTTP {response.status})")
                    if response.status != 200:
                        try:
                            error_text = await response.text()
                            logger.error(f"API returned status {response.status}: {error_text[:250]}")
                        except Exception:
                            logger.error(f"API returned status {response.status}")
                        return None

                    content_type = (response.headers.get("Content-Type") or "").lower()
                    content_length = response.headers.get("Content-Length")
                    if content_length:
                        logger.info(f"📦 API file size: {int(content_length) / 1048576:.2f} MB")
                    if "json" in content_type or "html" in content_type:
                        logger.error(f"API returned unexpected content type: {content_type}")
                        return None

                    downloaded = 0
                    last_log = 0
                    first_byte_at = None
                    transfer_started = None
                    with open(part_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(1024 * 1024):
                            if not chunk:
                                continue
                            if first_byte_at is None:
                                first_byte_at = time.monotonic()
                                transfer_started = first_byte_at
                                logger.info(f"⚡ [API TIMING] First audio bytes received for {video_id} after {first_byte_at - api_started:.2f}s (API preparation/TTFB: {first_byte_at - api_started:.2f}s)")
                            f.write(chunk)
                            downloaded += len(chunk)
                            if downloaded - last_log >= 10 * 1024 * 1024:
                                elapsed = max(time.monotonic() - transfer_started, 0.001)
                                speed = (downloaded / 1048576) / elapsed
                                logger.info(f"📊 API progress: {downloaded / 1048576:.1f} MB ({speed:.2f} MB/s)")
                                last_log = downloaded

                    api_finished = time.monotonic()
                    transfer_elapsed = (api_finished - transfer_started) if transfer_started else 0.0
                    transfer_speed = (downloaded / 1048576) / max(transfer_elapsed, 0.001) if downloaded else 0.0
                    logger.info(f"🏁 [API TIMING] Transfer finished for {video_id}: {downloaded / 1048576:.2f} MB in {transfer_elapsed:.2f}s ({transfer_speed:.2f} MB/s)")
                    logger.info(f"⏱️ [API TIMING] API total: {api_finished - api_started:.2f}s (headers {header_wait:.2f}s + transfer {transfer_elapsed:.2f}s)")

            if downloaded <= 1024 or not os.path.exists(part_path):
                logger.error("❌ API direct download returned an empty/invalid file")
                try:
                    os.remove(part_path)
                except OSError:
                    pass
                return None

            os.replace(part_path, file_path)
            file_size_mb = os.path.getsize(file_path) / 1048576
            logger.info(f"✅ [API DIRECT SUCCESS] Downloaded: {file_path} ({file_size_mb:.2f} MB)")
            return file_path

        except asyncio.TimeoutError:
            logger.error(f"⏰ Direct API timeout for {video_id} after {self.api_stream_timeout} seconds")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"🌐 Direct API client error for {video_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Direct API download failed for {video_id}: {type(e).__name__}: {e}")
            return None
        finally:
            if os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except OSError:
                    pass

    async def download_via_cookies(self, video_id: str, video: bool = False) -> Optional[str]:
        """
        Download audio/video using yt-dlp with cookies (Fallback Method).
        
        Args:
            video_id: YouTube video ID
            video: True for video download, False for audio download
        
        Returns:
            Path to downloaded file or None if failed
        """
        if not self.enable_cookies_fallback:
            logger.debug("Cookies fallback is disabled in config")
            return None

        url = self.base + video_id
        filename_pattern = f"downloads/{video_id}"
        
        # Check existing files
        existing_files = [
            f for f in glob.glob(f"{filename_pattern}.*")
            if not f.endswith('.part')
        ]
        
        if video:
            video_candidates = [
                f for f in existing_files
                if Path(f).suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}
            ]
            if video_candidates:
                logger.debug(f"Found existing video file: {video_candidates[0]}")
                return video_candidates[0]
        else:
            audio_candidates = [
                f for f in existing_files
                if Path(f).suffix.lower() in {".m4a", ".webm", ".opus", ".mp3", ".ogg", ".wav", ".flac"}
            ]
            if audio_candidates:
                logger.debug(f"Found existing audio file: {audio_candidates[0]}")
                return audio_candidates[0]

            container_fallbacks = [
                f for f in existing_files
                if Path(f).suffix.lower() in {".mp4", ".mkv", ".mov"}
            ]
            if container_fallbacks:
                logger.debug(f"Found existing container file: {container_fallbacks[0]}")
                return container_fallbacks[0]
        
        # Create downloads directory
        downloads_dir = Path("downloads")
        if not downloads_dir.exists():
            try:
                downloads_dir.mkdir(parents=True, exist_ok=True)
                logger.info("📁 Created downloads directory")
            except Exception as e:
                logger.error(f"❌ Cannot create downloads directory: {e}")
                return None

        async with self._download_semaphore:
            cookie = self.get_cookies()
            base_opts = {
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "quiet": True,
                "noplaylist": True,
                "geo_bypass": True,
                "no_warnings": True,
                "overwrites": False,
                "nocheckcertificate": True,
                "continuedl": True,
                "noprogress": True,
                "concurrent_fragment_downloads": 4,
                "http_chunk_size": 524288,
                "socket_timeout": 30,
                "retries": 2,
                "fragment_retries": 2,
                "extractor_retries": 5,
                "sleep_interval_requests": 0,
                "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            }

            if video:
                height_filter = ""
                if self._max_video_height and self._max_video_height > 0:
                    height_filter = f"[height<={self._max_video_height}]"
                format_chain = (
                    f"bestvideo[ext=mp4]{height_filter}+bestaudio[ext=m4a]/"
                    f"bestvideo{height_filter}+bestaudio/"
                    "bestvideo+bestaudio/best"
                )
                ydl_opts = {
                    **base_opts,
                    "format": format_chain,
                    "merge_output_format": "mp4",
                    "postprocessors": [
                        {
                            "key": "FFmpegVideoConvertor",
                            "preferedformat": "mp4",
                        }
                    ],
                }
            else:
                ydl_opts = {
                    **base_opts,
                    "format": "bestaudio[ext=m4a]/bestaudio[acodec=opus]/bestaudio/best",
                    "postprocessors": [],
                }

            ydl_opts_cookie = {
                **ydl_opts,
                "cookiefile": cookie,
            }

            def _download(ydl_runtime_opts):
                ydl_instance = None
                try:
                    ydl_instance = yt_dlp.YoutubeDL(ydl_runtime_opts)
                    info = ydl_instance.extract_info(url, download=True)
                    if not info:
                        logger.error(f"❌ Failed to extract info for {video_id}")
                        return None
                    
                    located = self._locate_download_file(video_id, video=video)
                    if located:
                        logger.info(f"✅ Download completed: {located}")
                        return located
                    
                    logger.error(f"❌ Download completed but file not found for: {video_id}")
                    return None
                except Exception as ex:
                    logger.warning(f"⚠️ Download error for {video_id}: {ex}")
                    recovered = self._locate_download_file(video_id, video=video)
                    if recovered:
                        logger.info(f"✅ Recovered existing file: {recovered}")
                        return recovered
                    return None
                finally:
                    if ydl_instance:
                        try:
                            ydl_instance.close()
                        except Exception:
                            pass

            logger.info(f"🍪 [COOKIES FALLBACK] Downloading {video_id} with cookies...")
            result = await asyncio.to_thread(_download, ydl_opts_cookie)
            
            if result:
                logger.info(f"✅ [COOKIES SUCCESS] Downloaded: {result}")
            else:
                logger.warning(f"⚠️ [COOKIES FAILED] Could not download {video_id}")
            
            return result

    def valid(self, url: str) -> bool:
        """Check if URL is a valid YouTube URL."""
        return bool(re.match(self.regex, url))

    def url(self, message_1: types.Message) -> Union[str, None]:
        """Extract YouTube URL from message."""
        messages = [message_1]
        link = None
        
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)

        for message in messages:
            text = message.text or message.caption or ""

            if message.entities:
                for entity in message.entities:
                    if entity.type == enums.MessageEntityType.URL:
                        link = text[entity.offset: entity.offset + entity.length]
                        break

            if message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == enums.MessageEntityType.TEXT_LINK:
                        link = entity.url
                        break

        if link:
            # Remove tracking parameters
            return link.split("&si")[0].split("?si")[0]
        return None


    async def search_related(self, title: str, channel_name: str = None, exclude_id: str = None, limit: int = 8) -> "Track | None":
        """
        Search for a DIFFERENT related song — YouTube-style autoplay.
        Tries multiple query variations, gets multiple results, and randomly picks
        one that is not the currently-playing song.
        """
        # Build varied search queries so we get different results each time
        queries = []
        if channel_name:
            queries.append(f"{channel_name} songs")
        # Strip common suffixes/prefixes that would pin us to the exact song
        clean_title = re.sub(r"\s*[-|].*", "", title).strip()  # "Song - Artist" → "Song"
        queries += [
            f"{clean_title} similar songs",
            f"songs like {clean_title}",
            f"{clean_title} best songs",
        ]
        if channel_name:
            queries.append(f"{channel_name} best songs")

        tried = set()
        for query in queries:
            if query in tried:
                continue
            tried.add(query)
            try:
                _search = VideosSearch(query, limit=limit)
                results = await _search.next()
            except Exception as e:
                logger.debug(f"search_related query failed '{query}': {e}")
                continue

            if not results or not results.get("result"):
                continue

            # Filter out the currently-playing song, missing IDs, and shuffle for variety
            candidates = [
                r for r in results["result"]
                if r.get("id") and r.get("link") and r.get("id") != exclude_id
            ]
            if not candidates:
                continue  # all results were excluded — try next query

            random.shuffle(candidates)
            data = candidates[0]

            duration = data.get("duration")
            is_live = duration is None or duration == "LIVE"
            track = Track(
                id=data.get("id"),
                channel_name=data.get("channel", {}).get("name"),
                duration=duration if not is_live else "LIVE",
                duration_sec=0 if is_live else utils.to_seconds(duration),
                message_id=0,
                title=data.get("title")[:25],
                ytitle=data.get("title"),
                thumbnail=data.get("thumbnails", [{}])[-1].get("url", "").split("?")[0],
                url=data.get("link"),
                view_count=data.get("viewCount", {}).get("short"),
                is_live=is_live,
            )
            return track

        return None

    async def search(self, query: str, m_id: int) -> Track | None:
        """Search for a song on YouTube."""
        cache_key = query
        current_time = asyncio.get_running_loop().time()

        # Check cache
        if cache_key in self.search_cache:
            cached_result, cache_timestamp = self.search_cache[cache_key]
            if current_time - cache_timestamp < 600:  # 10 minutes TTL
                fresh = replace(cached_result)
                fresh.message_id = m_id
                fresh.file_path = None
                fresh.user = None
                fresh.time = 0
                fresh.video = False
                return fresh

        try:
            _search = VideosSearch(query, limit=1)
            results = await _search.next()
        except Exception as e:
            logger.warning(f"⚠️ YouTube search failed for '{query}': {e}")
            return None

        if results and results["result"]:
            data = results["result"][0]
            duration = data.get("duration")
            is_live = duration is None or duration == "LIVE"

            track = Track(
                id=data.get("id"),
                channel_name=data.get("channel", {}).get("name"),
                duration=duration if not is_live else "LIVE",
                duration_sec=0 if is_live else utils.to_seconds(duration),
                message_id=m_id,
                title=data.get("title")[:25],
                ytitle=data.get("title"),
                thumbnail=data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                url=data.get("link"),
                view_count=data.get("viewCount", {}).get("short"),
                is_live=is_live,
            )

            # Cache result
            self.search_cache[cache_key] = (track, current_time)
            
            # Clean old cache entries
            if len(self.search_cache) > 100:
                oldest_key = min(self.search_cache.keys(),
                                 key=lambda k: self.search_cache[k][1])
                del self.search_cache[oldest_key]

            return replace(track)
        return None

    async def playlist(self, limit: int, user: str, url: str) -> list[Track]:
        """Extract tracks from a YouTube playlist."""
        try:
            plist = await Playlist.get(url)
            tracks = []

            if not plist or "videos" not in plist or not plist["videos"]:
                return []

            for data in plist["videos"][:limit]:
                try:
                    thumbnails = data.get("thumbnails", [])
                    thumbnail_url = ""
                    if thumbnails and len(thumbnails) > 0:
                        thumbnail_url = thumbnails[-1].get("url", "").split("?")[0]

                    link = data.get("link", "")
                    if "&list=" in link:
                        link = link.split("&list=")[0]

                    track = Track(
                        id=data.get("id", ""),
                        channel_name=data.get("channel", {}).get("name", ""),
                        duration=data.get("duration", "0:00"),
                        duration_sec=utils.to_seconds(data.get("duration", "0:00")),
                        title=(data.get("title", "Unknown")[:25]),
                        ytitle=data.get("title", "Unknown"),
                        thumbnail=thumbnail_url,
                        url=link,
                        user=user,
                        view_count="",
                    )
                    tracks.append(track)
                except Exception as e:
                    logger.warning(f"Failed to parse playlist item: {e}")
                    continue

            return tracks
        except KeyError as e:
            raise Exception(f"Failed to parse playlist. YouTube may have changed their structure.")
        except Exception as e:
            logger.error(f"Playlist extraction error: {e}")
            raise

    async def download(self, video_id: str, is_live: bool = False, video: bool = False) -> Optional[str]:
        """
        Download audio/video from YouTube.
        
        PRIORITY: API First → Cookies Fallback
        
        Args:
            video_id: YouTube video ID
            is_live: Whether it's a live stream
            video: True for video download, False for audio download
        
        Returns:
            Path to downloaded file or None if failed
        """
        # For live streams, only cookies method works
        if is_live:
            logger.info(f"🔴 Live stream detected for {video_id}, using cookies method...")
            cookie = self.get_cookies()
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "cookiefile": cookie,
                "format": "bestaudio/best",
                "noplaylist": True,
                "socket_timeout": 20,
                "extractor_retries": 5,
                "sleep_interval_requests": 0,
                "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            }

            def _extract_url():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        info = ydl.extract_info(self.base + video_id, download=False)
                        if not info:
                            return None

                        direct = info.get("url")
                        if direct:
                            return direct

                        for fmt in info.get("formats", []):
                            if fmt.get("acodec") != "none" and fmt.get("url"):
                                return fmt["url"]

                        return info.get("manifest_url")
                    except Exception as ex:
                        logger.error(f"Live stream extraction failed: {ex}")
                        return None

            try:
                stream_url = await asyncio.wait_for(asyncio.to_thread(_extract_url), timeout=35)
                if stream_url:
                    logger.info(f"✅ Live stream URL extracted for {video_id}")
                return stream_url
            except asyncio.TimeoutError:
                logger.error(f"Live stream URL extraction timed out for {video_id}")
                return None

        # Normal video/audio download - FAST yt-dlp FIRST, then cookies, then API.
        # The previous API-first path could spend 10-20+ seconds waiting for the
        # remote API to prepare the media before any bytes were returned.
        result = None

        # PRIORITY 1: direct yt-dlp without cookies. This avoids the remote API
        # preparation delay and lets YouTube's media URL be used directly.
        logger.info(f"⚡ [PRIORITY 1] Trying fast direct yt-dlp for {video_id}")
        result = await self._download_fast_ytdlp(video_id, video=video, use_cookies=False)
        if result:
            logger.info(f"✅ [FAST SUCCESS] Downloaded via direct yt-dlp: {video_id}")
            return result
        logger.warning(f"⚠️ [FAST FAILED] {video_id}")

        # PRIORITY 2: existing cookie downloader.
        if self.enable_cookies_fallback:
            logger.info(f"🍪 [PRIORITY 2] Trying cookies download for {video_id}")
            result = await self.download_via_cookies(video_id, video=video)
            if result:
                logger.info(f"✅ [SUCCESS] Downloaded via cookies: {video_id}")
                return result
            logger.warning(f"⚠️ [COOKIES FAILED] Could not download {video_id}")

        # PRIORITY 3: remote API as a final fallback. It remains available but
        # is no longer on the critical path for normal successful downloads.
        if self.enable_api and self.api_url and self.artistbots_key:
            logger.info(f"🌐 [PRIORITY 3] Trying API fallback for {video_id}")
            result = await self.download_via_api(self.base + video_id, video=video)
            if result:
                logger.info(f"✅ [SUCCESS] Downloaded via API fallback: {video_id}")
                return result
            logger.warning(f"⚠️ [API FAILED] {video_id}")

        logger.error(f"❌ [FAILED] All download methods failed for {video_id}")
        return result

    async def _download_fast_ytdlp(self, video_id: str, video: bool = False, use_cookies: bool = False) -> Optional[str]:
        """Fast direct yt-dlp downloader used before remote API fallback."""
        url = self.base + video_id
        downloads_dir = Path("downloads")
        downloads_dir.mkdir(parents=True, exist_ok=True)

        cookie = self.get_cookies() if use_cookies else None
        base_opts = {
            "outtmpl": "downloads/%(id)s.%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "continuedl": True,
            "noprogress": True,
            "socket_timeout": 12,
            "retries": 1,
            "fragment_retries": 1,
            "extractor_retries": 2,
            "sleep_interval_requests": 0,
            "concurrent_fragment_downloads": 4,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web_embedded"]
                }
            },
        }
        if cookie:
            base_opts["cookiefile"] = cookie

        if video:
            height_filter = ""
            if self._max_video_height and self._max_video_height > 0:
                height_filter = f"[height<={self._max_video_height}]"
            ydl_opts = {
                **base_opts,
                "format": (
                    f"bestvideo[ext=mp4]{height_filter}+bestaudio[ext=m4a]/"
                    f"bestvideo{height_filter}+bestaudio/best"
                ),
                "merge_output_format": "mp4",
            }
        else:
            ydl_opts = {
                **base_opts,
                "format": "bestaudio[ext=m4a]/bestaudio[acodec=opus]/bestaudio/best",
            }

        started = time.monotonic()

        def _run():
            ydl = None
            try:
                ydl = yt_dlp.YoutubeDL(ydl_opts)
                info = ydl.extract_info(url, download=True)
                if not info:
                    return None
                return self._locate_download_file(video_id, video=video)
            except Exception as exc:
                logger.warning(f"⚠️ [FAST YTDLP] {video_id}: {exc}")
                recovered = self._locate_download_file(video_id, video=video)
                return recovered
            finally:
                if ydl:
                    try:
                        ydl.close()
                    except Exception:
                        pass

        try:
            result = await asyncio.to_thread(_run)
            elapsed = time.monotonic() - started
            if result:
                logger.info(f"⚡ [FAST YTDLP TIMING] {video_id}: {elapsed:.2f}s")
            else:
                logger.warning(f"⚠️ [FAST YTDLP TIMING] {video_id}: failed after {elapsed:.2f}s")
            return result
        except Exception as exc:
            logger.warning(f"⚠️ [FAST YTDLP] Unexpected error for {video_id}: {exc}")
            return None
