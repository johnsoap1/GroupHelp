"""
Music Downloader Module for Telegram

A high-performance music downloader with caching support for Telegram bots.
Supports YouTube and YouTube Music with automatic format conversion to MP3.

Features:
- Multi-source fallback (YouTube → YouTube Music → SoundCloud)
- Smart caching with exact query matching
- Support for age-restricted content via cookies
- MP3 format for maximum compatibility
- Automatic command cleanup
- Robust error recovery
- Auto ffmpeg/ffprobe detection
"""
import os
import re
import datetime
import asyncio
import hashlib
import json
import random
import shutil
import signal
import tempfile
import time
import atexit
import subprocess
import traceback
from functools import partial
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

# Bot imports
from wbb import app, arq, SUDOERS, db
from pyrogram import filters
from pyrogram.types import InlineQuery, InlineQueryResultAudio, Message
from yt_dlp import YoutubeDL

# ==================== MODULE INFO ====================

__MODULE__ = "Music"
__HELP__ = """
🎵 **Music Downloader**

Download music from YouTube, YouTube Music, and SoundCloud with smart caching.

**Commands:**
- `/song <query>` - Search and download songs (MP3, cached)
- `/song! <query>` - Force fresh download (bypass cache)
- `/ytmusic <query/link>` - YouTube Music download
- `/lyrics <song>` - Get song lyrics

**Admin Commands:**
- `/cacheinfo` - Show cache statistics
- `/cachelist` - List recent cached songs
- `/purge <query>` - Delete cached entries
- `/teststorage` - Test storage configuration

**Features:**
✅ Multi-source fallback (YouTube → YouTube Music → SoundCloud)
✅ Smart caching with exact query matching
✅ Age-restricted video support via cookies
✅ MP3 format for maximum compatibility
✅ Automatic command cleanup
✅ Robust error recovery

**Setup:**
1. Set `MUSIC_GROUP_ID` or `MUSIC_CHANNEL_ID` in config.env
2. (Optional) Place cookies.txt in `/root/cookies/` for age-restricted content
3. Ensure bot is admin in storage location with send permissions

**Examples:**
`/song shape of you`
`/song! levitating dua lipa`
`/ytmusic blinding lights`
`/lyrics imagine dragons believer`

**Note:** Use `/song!` to force re-download if cache has wrong song.
"""

# ==================== BASIC ERROR HANDLER ====================

def capture_err(func):
    """Simple error handler decorator for command handlers."""
    async def wrapper(client, message, *args, **kwargs):
        try:
            return await func(client, message, *args, **kwargs)
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
            print(f"Error in {func.__name__}: {error_message}")
            try:
                await message.reply_text(f"❌ {error_message[:200]}")
            except Exception as ex:
                print(f"Failed to send error message: {ex}")
    return wrapper

# ==================== CONFIGURATION ====================

# Storage configuration
MUSIC_GROUP_ID = int(os.getenv("MUSIC_GROUP_ID", "0")) or None
MUSIC_CHANNEL_ID = int(os.getenv("MUSIC_CHANNEL_ID", "0")) or None

# Limits
MAX_DURATION = 3600          # 1 hour
MAX_FILESIZE_MB = 100
MIN_FILESIZE_BYTES = 50_000  # 50 KB minimum valid file

# Directories
TEMP_DIR = Path(tempfile.gettempdir()) / "wbb_music"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
COOKIES_PATH = Path("/root/cookies/cookies.txt")

# Concurrency
GLOBAL_SEM = asyncio.Semaphore(10)

# Per-source timeout (shorter = faster fallback on failure)
SOURCE_TIMEOUT = 35   # seconds per source attempt
DOWNLOAD_TIMEOUT = 120  # overall hard cap

# ==================== FFMPEG AUTO-DETECTION ====================

def _find_ffmpeg_location() -> Optional[str]:
    """
    Locate the directory containing ffmpeg & ffprobe.
    Checks common install paths first, then falls back to PATH.
    Returns the parent directory string (what yt-dlp expects), or None.
    """
    common_paths = [
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
        "/snap/bin/ffmpeg",
    ]
    for path in common_paths:
        if Path(path).exists():
            return str(Path(path).parent)

    found = shutil.which("ffmpeg")
    if found:
        return str(Path(found).parent)

    return None

FFMPEG_LOCATION: Optional[str] = _find_ffmpeg_location()

# Log ffmpeg status at module load so problems are obvious immediately
_ffmpeg_bin = shutil.which("ffmpeg")
_ffprobe_bin = shutil.which("ffprobe")
print(f"[STARTUP] ffmpeg  : {_ffmpeg_bin  or 'NOT FOUND ⚠️'}")
print(f"[STARTUP] ffprobe : {_ffprobe_bin or 'NOT FOUND ⚠️'}")
print(f"[STARTUP] ffmpeg_location for yt-dlp: {FFMPEG_LOCATION or 'NOT FOUND ⚠️'}")

if not FFMPEG_LOCATION:
    print("[STARTUP] ⚠️  ffmpeg not found — audio post-processing WILL fail. "
          "Install ffmpeg or set --ffmpeg-location manually.")

# ==================== DATABASE ====================

cache_col = db.music_cache

# ==================== USER AGENTS ====================

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# ==================== HELPER FUNCTIONS ====================

def setup_ytdlp_config():
    """Create clean yt-dlp config to prevent interference."""
    config_dir = Path.home() / ".config" / "yt-dlp"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config"
    if not config_file.exists():
        config_file.write_text("# Auto-generated - minimal config\n")

setup_ytdlp_config()

def human_time(sec: int) -> str:
    return str(datetime.timedelta(seconds=int(sec)))

def safe_filename(s: str) -> str:
    return "".join(c for c in s if c.isalnum() or c in (" ", "-", "_", ".", "(", ")")).strip()[:180]

def sanitize_template(name: str) -> str:
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_%.(){}")
    return "".join(ch if ch in allowed else "_" for ch in name)

def normalize_query(query: str) -> str:
    return re.sub(r'\s+', ' ', query.lower().strip())

def normalize_song_query(q: str) -> str:
    """Clean up search query for better results."""
    if q.startswith(("http://", "https://")):
        return q
    q = re.sub(r'\(.*?\)|\[.*?\]', '', q)
    q = re.sub(
        r'\b(lyrics|official.*?video?|official.*?audio|official|video|audio|hd|hq|4k|full|song|track)\b',
        '', q, flags=re.IGNORECASE
    )
    q = ' '.join(q.split()).strip()
    if len(q.split()) <= 2:
        q += " official audio"
    return q

def is_sudo(user_id: int) -> bool:
    return user_id in SUDOERS

def is_valid_audio(path: Path) -> bool:
    return path.exists() and path.stat().st_size >= MIN_FILESIZE_BYTES

def debug_file_info(file_path: str, prefix: str = "") -> bool:
    try:
        p = Path(file_path)
        if not p.exists():
            print(f"[DEBUG {prefix}] ❌ File does not exist: {file_path}")
            return False
        size = p.stat().st_size
        print(f"[DEBUG {prefix}] ✓ {file_path} — {size:,} bytes ({size/1024/1024:.2f} MB)")
        return is_valid_audio(p)
    except Exception as e:
        print(f"[DEBUG {prefix}] ❌ Error: {e}")
        return False

# ==================== CACHE MANAGEMENT ====================

async def get_cached_song(query: str, exact_only: bool = True) -> Optional[Dict]:
    """Lookup a cached song.

    If `exact_only` is False, perform a fuzzy regex search against
    `query`, `title`, and `performer` for better hit rates on seeded files.
    """
    query_norm = normalize_query(query)
    # Try exact match first
    data = await cache_col.find_one({"query": query_norm})
    if not data and not exact_only:
        # fuzzy search across query/title/performer
        regex = {"$regex": query_norm, "$options": "i"}
        data = await cache_col.find_one({"$or": [{"query": regex}, {"title": regex}, {"performer": regex}]})

    if data:
        # update access metadata
        key = {"query": data.get("query")} if data.get("query") else {"file_unique_id": data.get("file_unique_id")}
        await cache_col.update_one(
            key,
            {
                "$set": {"last_accessed": datetime.datetime.utcnow()},
                "$inc": {"access_count": 1}
            }
        )
        print(f"[CACHE] Hit: '{data.get('query') or data.get('file_unique_id')}' ({data.get('access_count', 0) + 1} plays)")
        return data

    print(f"[CACHE] Miss: '{query_norm}'")
    return None

async def save_cached_song(query: str, title: str, performer: str,
                           duration: int, file_id: str,
                           thumb_file_id: Optional[str], storage_msg_id: int,
                           file_unique_id: Optional[str] = None,
                           source: str = "downloaded"):
    """Save or update a cached song.

    If `file_unique_id` is provided, use it to detect duplicates and
    update the existing entry instead of creating new ones.
    """
    normalized_query = normalize_query(query)

    doc = {
        "query": normalized_query,
        "original_query": query,
        "title": title,
        "performer": performer,
        "duration": duration,
        "file_id": file_id,
        "thumb_file_id": thumb_file_id,
        "storage_msg_id": storage_msg_id,
        "file_unique_id": file_unique_id,
        "source": source,
        "created_at": datetime.datetime.utcnow(),
        "last_accessed": datetime.datetime.utcnow(),
    }

    if file_unique_id:
        # Upsert by unique file id to prevent duplicates from manual seeding
        await cache_col.update_one({"file_unique_id": file_unique_id}, {"$set": doc, "$setOnInsert": {"access_count": 1}}, upsert=True)
        print(f"[CACHE] Saved/Updated by file_unique_id: {file_unique_id[:20]}...")
    else:
        await cache_col.update_one({"query": normalized_query}, {"$set": doc, "$setOnInsert": {"access_count": 1}}, upsert=True)
        print(f"[CACHE] Saved: '{normalized_query}' → file_id: {file_id[:20]}...")

async def delete_cached_song(query: str):
    await cache_col.delete_one({"query": normalize_query(query)})

# ==================== YT-DLP OPTIONS ====================

def get_base_opts(cookiefile: Optional[str] = None) -> Dict:
    """
    Base yt-dlp options shared by all audio download functions.
    Critically includes ffmpeg_location so yt-dlp finds the binaries
    even when the bot process PATH differs from the system PATH.
    """
    opts: Dict = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": str(TEMP_DIR / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "cachedir": False,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            },
            {"key": "FFmpegMetadata"},
        ],
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "extract_flat": False,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/129.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
        },
        "geo_bypass": True,
        "nocheckcertificate": True,
        "ignore_no_formats_error": True,
        "extractor_retries": 3,
        "noprogress": True,
    }

    # ── KEY FIX: tell yt-dlp exactly where ffmpeg lives ──────────────────────
    if FFMPEG_LOCATION:
        opts["ffmpeg_location"] = FFMPEG_LOCATION
    # ─────────────────────────────────────────────────────────────────────────

    if cookiefile and Path(cookiefile).exists():
        opts["cookiefile"] = cookiefile
        print(f"[YT-DLP] Using cookies: {cookiefile}")

    return opts

def get_audio_opts(tmpdir: Path, cookiefile: Optional[str] = None) -> Dict:
    """Audio download options targeting MP3 output."""
    opts = get_base_opts(cookiefile)
    opts.update({
        # Prefer opus webm first, then m4a, then any best audio.
        "format": "bestaudio[ext=webm][acodec=opus]/bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": str(tmpdir / "%(id)s.%(ext)s"),
        "postprocessors": [],
        "concurrent_fragment_downloads": 4,
        "postprocessor_args": [
            "-ac", "2",
            "-ar", "44100",
            "-threads", "2",
        ],
    })
    return opts

def get_video_opts(tmpdir: Path, cookiefile: Optional[str] = None) -> Dict:
    opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
        "outtmpl": str(tmpdir / sanitize_template("%(id)s.%(ext)s")),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "cachedir": False,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "merge_output_format": "mp4",
        "prefer_ffmpeg": True,
        "http_headers": {"User-Agent": random.choice(USER_AGENTS)},
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
            {"key": "FFmpegMetadata"},
        ],
        "postprocessor_args": ["-movflags", "+faststart", "-pix_fmt", "yuv420p"],
        "fixup": "detect_or_warn",
    }
    if FFMPEG_LOCATION:
        opts["ffmpeg_location"] = FFMPEG_LOCATION
    if cookiefile and Path(cookiefile).exists():
        opts["cookiefile"] = cookiefile
    return opts

# ==================== SEARCH QUERY BUILDERS ====================

def build_yt_search(query: str) -> str:
    if query.startswith(("http://", "https://")):
        return query
    # Use ytsearch1 to avoid duplicate extraction work elsewhere
    return f"ytsearch1:{normalize_song_query(query)}"

def build_ytmusic_search(query: str) -> str:
    if query.startswith(("http://", "https://")):
        return query
    return f"ytsearch1:{normalize_song_query(query)} topic"

def build_soundcloud_search(query: str) -> str:
    if query.startswith(("http://", "https://")):
        return query
    return f"scsearch1:{normalize_song_query(query)}"

# ==================== DOWNLOAD FUNCTIONS ====================

def _pick_entry(entries: List[Dict]) -> Dict:
    """
    Pick the best entry from a search result list.
    Prefers tracks over 60 s; falls back to first entry.
    """
    valid = [e for e in entries if e and e.get("duration", 0) > 60]
    return valid[0] if valid else entries[0]

def _download_blocking(search: str, opts: Dict, tmpdir: Path,
                       allowed_exts: List[str]) -> Dict:
    """
    Blocking download — runs in a thread executor.

    Key improvement over original: we call extract_info with download=True
    only ONCE (after picking the entry from the playlist). This eliminates
    the double round-trip that was doubling latency.
    """
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(search, download=False)

        if "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise RuntimeError("Search returned no entries")
            selected = _pick_entry(entries)
            url = selected.get("webpage_url") or selected.get("url")
            if not url:
                raise RuntimeError("Selected entry has no download URL")
            info = ydl.extract_info(url, download=True)
        else:
            # Direct URL — use already-fetched metadata if available, then download once
            url = info.get("webpage_url") or info.get("url") or search
            info = ydl.extract_info(url, download=True)

    # Locate the output file
    files: List[Path] = []
    for ext in allowed_exts:
        files.extend(tmpdir.glob(f"*{ext}"))
        if files:
            break

    if not files:
        files = [f for f in tmpdir.iterdir() if f.is_file() and f.suffix not in (".part", ".ytdl")]

    if not files:
        raise RuntimeError(f"Download produced no files (expected: {allowed_exts})")

    file = max(files, key=lambda f: f.stat().st_size)

    file = files[0]
    if not is_valid_audio(file):
        raise RuntimeError(f"Downloaded file is invalid or too small: {file.name}")

    return {
        "file": str(file),
        "title": info.get("title", file.stem)[:64],
        "performer": (info.get("artist") or info.get("uploader") or "Unknown")[:64],
        "duration": int(info.get("duration") or 0),
        "tmpdir": str(tmpdir),
        "thumb_url": info.get("thumbnail"),
    }

def _download_video_blocking(search: str, tmpdir: Path,
                             cookiefile: Optional[str]) -> Dict:
    opts = get_video_opts(tmpdir, cookiefile)

    def run(current_opts: Dict) -> Dict:
        with YoutubeDL(current_opts) as ydl:
            extracted = ydl.extract_info(search, download=True)
        if "entries" in extracted:
            extracted = extracted["entries"][0]
        return extracted

    try:
        info = run(opts)
    except Exception:
        fallback = {**opts, "format": "best"}
        info = run(fallback)

    files: List[Path] = []
    for ext in (".mp4", ".mkv", ".webm"):
        files.extend(tmpdir.glob(f"*{ext}"))
        if files:
            break

    if not files:
        raise RuntimeError("Download produced no video files")

    file_path = files[0]
    return {
        "file": str(file_path),
        "title": info.get("title", file_path.stem)[:100],
        "duration": int(info.get("duration") or 0),
        "uploader": (info.get("uploader") or info.get("channel") or "Unknown")[:64],
        "width": info.get("width"),
        "height": info.get("height"),
        "tmpdir": str(tmpdir),
    }

# ── Per-source downloaders ────────────────────────────────────────────────────

async def _run_download(search: str, opts: Dict, tmpdir: Path,
                        allowed_exts: List[str]) -> Dict:
    """Async wrapper: runs blocking download in executor with SOURCE_TIMEOUT."""
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(
            None,
            partial(_download_blocking, search, opts, tmpdir, allowed_exts)
        ),
        timeout=SOURCE_TIMEOUT,
    )

async def download_audio_youtube(query: str, cookiefile: Optional[str] = None) -> Dict:
    tmpdir = TEMP_DIR / f"yt_{int(time.time())}_{random.randint(1000, 9999)}"
    tmpdir.mkdir(parents=True, exist_ok=True)
    try:
        opts = get_audio_opts(tmpdir, cookiefile)
        result = await _run_download(
            build_yt_search(query), opts, tmpdir, [".m4a", ".mp3", ".webm"]
        )
        print("[YOUTUBE] ✅ Download successful")
        return result
    except Exception as e:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise

async def download_audio_ytmusic(query: str, cookiefile: Optional[str] = None) -> Dict:
    tmpdir = TEMP_DIR / f"ytm_{int(time.time())}_{random.randint(1000, 9999)}"
    tmpdir.mkdir(parents=True, exist_ok=True)
    try:
        opts = get_audio_opts(tmpdir, cookiefile)
        result = await _run_download(
            build_ytmusic_search(query), opts, tmpdir, [".m4a", ".mp3", ".webm"]
        )
        print("[YTMUSIC] ✅ Download successful")
        return result
    except Exception as e:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise

async def download_audio_soundcloud(query: str) -> Dict:
    tmpdir = TEMP_DIR / f"sc_{int(time.time())}_{random.randint(1000, 9999)}"
    tmpdir.mkdir(parents=True, exist_ok=True)
    try:
        opts = get_audio_opts(tmpdir)
        result = await _run_download(
            build_soundcloud_search(query), opts, tmpdir, [".m4a", ".mp3"]
        )
        print("[SOUNDCLOUD] ✅ Download successful")
        return result
    except Exception as e:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise

# ── Main entry point ─────────────────────────────────────────────────────────

async def download_audio(query: str, sources: List[str] = None) -> Dict:
    """
    Download audio with multi-source fallback.
    Each source gets SOURCE_TIMEOUT seconds before we move on —
    no more waiting 3 minutes per failed source.
    """
    if sources is None:
        sources = ["youtube", "ytmusic", "soundcloud"]

    cookiefile = str(COOKIES_PATH) if COOKIES_PATH.exists() else None
    last_error: Optional[Exception] = None

    for source in sources:
        try:
            print(f"[DOWNLOAD] Trying source: {source}")
            if source == "youtube":
                return await download_audio_youtube(query, cookiefile)
            elif source == "ytmusic":
                return await download_audio_ytmusic(query, cookiefile)
            elif source == "soundcloud":
                return await download_audio_soundcloud(query)
            else:
                print(f"[DOWNLOAD] Unknown source: {source}")
        except asyncio.TimeoutError:
            last_error = asyncio.TimeoutError(f"{source} timed out after {SOURCE_TIMEOUT}s")
            print(f"[DOWNLOAD] {source} timed out — trying next source")
        except Exception as e:
            last_error = e
            print(f"[DOWNLOAD] {source} failed: {str(e)[:120]}")

    raise RuntimeError(f"All sources failed. Last error: {str(last_error)[:200]}")

async def download_video(query: str) -> Dict:
    tmpdir = TEMP_DIR / f"vid_{int(time.time())}_{random.randint(1000, 9999)}"
    tmpdir.mkdir(parents=True, exist_ok=True)
    search = query if query.startswith(("http://", "https://")) else f"ytsearch1:{query}"
    cookiefile = str(COOKIES_PATH) if COOKIES_PATH.exists() else None
    loop = asyncio.get_running_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None, partial(_download_video_blocking, search, tmpdir, cookiefile)
            ),
            timeout=DOWNLOAD_TIMEOUT,
        )
        return result
    except Exception:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise

# ==================== STORAGE UPLOAD ====================

async def _download_thumb(url: str, tmpdir: Path) -> Optional[str]:
    """Download thumbnail URL to a local file. Returns local path or None."""
    if not url or not url.startswith("http"):
        return None

    try:
        import aiohttp
        thumb_path = tmpdir / "thumb.jpg"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    thumb_path.write_bytes(await resp.read())
                    return str(thumb_path)
    except Exception as e:
        print(f"[THUMB] Failed to download: {e}")
    return None


async def upload_to_storage(file_path: str, title: str, performer: str,
                            duration: int, thumb_path: Optional[str]) -> Message:
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        raise RuntimeError(f"File not found: {file_path}")

    file_size = file_path_obj.stat().st_size
    if file_size < MIN_FILESIZE_BYTES:
        raise RuntimeError(f"File too small ({file_size} bytes), likely corrupted")

    storage_id = MUSIC_GROUP_ID or MUSIC_CHANNEL_ID
    if not storage_id:
        raise RuntimeError("No storage configured. Set MUSIC_GROUP_ID or MUSIC_CHANNEL_ID")

    local_thumb: Optional[str] = None
    if thumb_path:
        if thumb_path.startswith("http"):
            local_thumb = await _download_thumb(thumb_path, file_path_obj.parent)
        elif Path(thumb_path).exists():
            local_thumb = str(Path(thumb_path))

    def _ffmpeg_path() -> Optional[str]:
        if FFMPEG_LOCATION:
            candidate = Path(FFMPEG_LOCATION) / "ffmpeg"
            if candidate.exists():
                return str(candidate)
        return shutil.which("ffmpeg")

    def transcode_to_mp3(in_path: str, out_path: str, bitrate: str = "128k") -> None:
        ff = _ffmpeg_path()
        if not ff:
            raise RuntimeError("ffmpeg not found for transcoding")
        cmd = [
            ff,
            "-y",
            "-i", in_path,
            "-ac", "2",
            "-ar", "44100",
            "-threads", "2",
            "-b:a", bitrate,
            out_path,
        ]
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {proc.stderr.decode(errors='ignore')[:200]}")

    async def _send(audio_path: str) -> Message:
        return await asyncio.wait_for(
            app.send_audio(
                chat_id=storage_id,
                audio=audio_path,
                caption=title,
                performer=performer,
                title=title,
                duration=duration,
                thumb=local_thumb,
                disable_notification=True,
            ),
            timeout=90,
        )

    mp3_path = str(file_path_obj.with_suffix('.mp3'))
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            partial(transcode_to_mp3, str(file_path_obj), mp3_path,
                    os.getenv('AUDIO_BITRATE', '128k'))
        )
        if not Path(mp3_path).exists():
            raise RuntimeError("Transcode produced no output file")

        sent = await _send(mp3_path)
        print("[STORAGE] ✅ Uploaded MP3")
        return sent
    except asyncio.TimeoutError:
        raise RuntimeError("Upload timed out after 90s")
    except Exception as e:
        raise RuntimeError(f"Failed to upload to storage: {str(e)[:200]}")
    finally:
        Path(mp3_path).unlink(missing_ok=True)


# ==================== STORAGE CHANNEL INDEXER ====================

@app.on_message(filters.chat(MUSIC_CHANNEL_ID) & filters.audio)
async def storage_audio_indexer(_, m: Message):
    """Auto-index any audio dropped into the configured storage channel.

    Seeds incoming audio into the Mongo cache so future `/song` requests
    can be served instantly.
    """
    try:
        audio = m.audio
        title = audio.title or "Unknown"
        performer = audio.performer or "Unknown"
        file_unique_id = getattr(audio, "file_unique_id", None)
        thumb_file_id = audio.thumbs[0].file_id if audio.thumbs else None

        query_variants = [f"{performer} {title}", title]

        for query in query_variants:
            await save_cached_song(
                query=query,
                title=title,
                performer=performer,
                duration=audio.duration or 0,
                file_id=audio.file_id,
                thumb_file_id=thumb_file_id,
                storage_msg_id=m.id,
                file_unique_id=file_unique_id,
                source="manual_seeded",
            )

        print(f"[INDEXED] {performer} - {title}")
    except Exception as e:
        print(f"[INDEXER ERROR] {e}")

# ==================== COMMAND HANDLERS ====================

@app.on_message(filters.command(["song", "song!"]) & filters.group)
@capture_err
async def song_handler(_, m: Message):
    """Handle /song and /song! commands."""
    if len(m.command) < 2:
        return await m.reply_text("📝 Usage: `/song <query>`\n\nUse `/song!` to force fresh download.")

    force = m.command[0].endswith("!")
    query = m.text.split(None, 1)[1].strip()
    msg = await m.reply_text(f"🔎 {'Forcing fresh download' if force else 'Searching'}: `{query}`...")

    try:
        # ── Cache lookup ────────────────────────────────────────────────────
        if not force:
            cached = await get_cached_song(query, exact_only=True)
            if cached:
                try:
                    file_id = cached.get("file_id")
                    title = cached.get("title")
                    await msg.edit(f"✅ Found in cache: **{title}**")
                    await m.reply_audio(file_id)
                    await msg.delete()
                    try:
                        await m.delete()
                    except Exception:
                        pass
                    print(f"[CACHE HIT] Served: {query}")
                    return
                except Exception as e:
                    print(f"[CACHE] Stale file_id, re-downloading: {e}")
                    await delete_cached_song(query)
            else:
                # Try fuzzy search across title/performer/query for seeded files
                fuzzy = await get_cached_song(query, exact_only=False)
                if fuzzy:
                    try:
                        file_id = fuzzy.get("file_id")
                        title = fuzzy.get("title")
                        await msg.edit(f"✅ Found in cache: **{title}**")
                        await m.reply_audio(file_id)
                        await msg.delete()
                        try:
                            await m.delete()
                        except Exception:
                            pass
                        print(f"[CACHE HIT-FUZZY] Served: {query} -> {title}")
                        return
                    except Exception as e:
                        print(f"[CACHE] Stale fuzzy file_id, re-downloading: {e}")
                        # try deleting normalized query entry only
                        await delete_cached_song(query)
        else:
            await delete_cached_song(query)
            await msg.edit("🔄 Cache cleared, downloading fresh...")

        # ── Download ────────────────────────────────────────────────────────
        async with GLOBAL_SEM:
            await msg.edit("⬇️ Downloading from YouTube...")
            result = await download_audio(query)

            if not result or not result.get("file"):
                raise RuntimeError("Download failed — no file returned")

            file_path = Path(result["file"])
            if not file_path.exists():
                raise RuntimeError(f"Downloaded file missing: {file_path}")
            if file_path.stat().st_size < MIN_FILESIZE_BYTES:
                raise RuntimeError("Downloaded file too small, likely corrupted")

            # ── Upload to storage & cache ───────────────────────────────────
            storage_id = MUSIC_GROUP_ID or MUSIC_CHANNEL_ID
            if storage_id:
                try:
                    await msg.edit("📤 Uploading to storage...")
                    sent = await asyncio.wait_for(
                        upload_to_storage(
                            result["file"],
                            result["title"],
                            result["performer"],
                            result["duration"],
                            result.get("thumb_url"),
                        ),
                        timeout=100,
                    )
                    await save_cached_song(
                        query,
                        result["title"],
                        result["performer"],
                        result["duration"],
                        sent.audio.file_id,
                        sent.audio.thumbs[0].file_id if sent.audio.thumbs else None,
                        sent.id,
                    )
                    await msg.edit("✅ Done! Sending...")
                    await m.reply_audio(sent.audio.file_id)
                    print(f"[CACHED] Saved: {query}")
                except asyncio.TimeoutError:
                    print("[STORAGE] Upload timed out, sending directly")
                    await msg.edit("⚠️ Storage slow, sending directly...")
                    await m.reply_audio(
                        result["file"],
                        title=result["title"],
                        performer=result["performer"],
                        duration=result["duration"],
                    )
                except Exception as e:
                    print(f"[STORAGE ERROR] {e}")
                    await msg.edit("⚠️ Storage failed, sending directly...")
                    await m.reply_audio(
                        result["file"],
                        title=result["title"],
                        performer=result["performer"],
                        duration=result["duration"],
                    )
            else:
                await msg.edit("✅ Sending...")
                await m.reply_audio(
                    result["file"],
                    title=result["title"],
                    performer=result["performer"],
                    duration=result["duration"],
                    thumb=result.get("thumb_url"),
                )
                print(f"[NO STORAGE] Sent directly: {query}")

            await msg.delete()
            try:
                await m.delete()
            except Exception:
                pass

            shutil.rmtree(result["tmpdir"], ignore_errors=True)

    except asyncio.TimeoutError:
        await msg.edit("❌ Download timed out. Try again later.")
    except Exception as e:
        await msg.edit(f"❌ Error: {str(e)[:200]}")
        print(f"[ERROR] /song: {e}")
        traceback.print_exc()


@app.on_message(filters.command("lyrics"))
async def lyrics_handler(_, m: Message):
    """Handle /lyrics command."""
    if len(m.command) < 2:
        return await m.reply_text("🎵 Usage: `/lyrics <song name>`")

    query = m.text.split(None, 1)[1].strip()
    msg = await m.reply_text("🔍 Searching lyrics...")

    try:
        if arq is None:
            return await msg.edit("❌ Lyrics service unavailable.")

        resp = await arq.lyrics(query)
        if not (resp.ok and resp.result):
            return await msg.edit("❌ No lyrics found.")

        song = resp.result[0]
        text = f"**{song['song']}** | **{song['artist']}**\n\n{song['lyrics']}"
        if len(text) > 4096:
            text = text[:4090] + "..."

        await msg.edit(text)
        try:
            await m.delete()
        except Exception:
            pass
    except Exception as e:
        await msg.edit(f"❌ Error: {str(e)[:200]}")
        print(f"[ERROR] /lyrics: {e}")


@app.on_message(filters.command("video") & (filters.group | filters.private))
@capture_err
async def video_handler(_, m: Message):
    """Universal video downloader."""
    if len(m.command) < 2:
        return await m.reply_text(
            "🎬 **Video Downloader**\n\nUsage:\n`/video <link>`\n`/video <artist title>`"
        )

    query = m.text.split(None, 1)[1].strip()
    msg = await m.reply_text(f"🎬 Downloading video...\n`{query}`")

    try:
        async with GLOBAL_SEM:
            result = await download_video(query)

        await msg.edit("📤 Uploading video...")
        file_path = Path(result["file"])
        safe_name = safe_filename(result["title"]) or file_path.stem

        try:
            await m.reply_video(
                video=str(file_path),
                supports_streaming=True,
                width=result.get("width"),
                height=result.get("height"),
                duration=result.get("duration") or None,
            )
        except Exception as send_err:
            print(f"[VIDEO] Falling back to document: {send_err}")
            await m.reply_document(
                document=str(file_path),
                file_name=f"{safe_name}{file_path.suffix or '.mp4'}",
            )

        await msg.delete()
        try:
            await m.delete()
        except Exception:
            pass

        shutil.rmtree(result["tmpdir"], ignore_errors=True)

    except asyncio.TimeoutError:
        await msg.edit("❌ Download timed out.")
    except Exception as e:
        await msg.edit(f"❌ Video failed:\n`{str(e)[:200]}`")

# ==================== CUSTOM FILTERS ====================

def sudo_filter(_, __, m: Message):
    if not SUDOERS:
        return True
    return m.from_user and (m.from_user.id in SUDOERS or m.from_user.is_self)

sudo_only = filters.create(sudo_filter, "SudoFilter")

# ==================== ADMIN COMMANDS ====================

@app.on_message(filters.command("cacheinfo") & sudo_only)
async def cache_info_handler(_, m: Message):
    try:
        audio_count = await cache_col.count_documents({})
        latest = await cache_col.find().sort("created_at", -1).limit(1).to_list(1)
        text = "📊 **Cache Statistics**\n\n"
        text += f"**🎵 Songs Cached:** {audio_count}\n"
        if latest:
            text += f"**Last Added:** {latest[0]['title']}\n"
        await m.reply_text(text)
    except Exception as e:
        await m.reply_text(f"❌ Error: {str(e)[:200]}")
        print(f"[ERROR] /cacheinfo: {e}")


@app.on_message(filters.command("cachelist") & sudo_only)
async def cache_list_handler(_, m: Message):
    if not is_sudo(m.from_user.id):
        return await m.reply_text("❌ Sudo only")
    try:
        data = cache_col.find().sort("last_accessed", -1).limit(15)
        text = "📋 **Recent Cached Songs**\n_Sorted by last access_\n\n"
        i = 1
        async for d in data:
            access_count = d.get("access_count", 0)
            last_access = d.get("last_accessed", d.get("created_at"))
            time_ago = datetime.datetime.utcnow() - last_access
            if time_ago.days > 0:
                time_str = f"{time_ago.days}d ago"
            elif time_ago.seconds > 3600:
                time_str = f"{time_ago.seconds // 3600}h ago"
            else:
                time_str = f"{time_ago.seconds // 60}m ago"
            text += f"{i}. **{d['title']}** - {d.get('performer', 'Unknown')}\n"
            text += f"   📊 {access_count} plays • 🕐 {time_str}\n"
            text += f"   `{d['query']}`\n\n"
            i += 1
        if i == 1:
            text = "📭 No cached songs yet"
        await m.reply_text(text)
    except Exception as e:
        await m.reply_text(f"❌ Error: {str(e)}")


@app.on_message(filters.command("purge") & sudo_only)
async def purge_handler(_, m: Message):
    if not is_sudo(m.from_user.id):
        return await m.reply_text("❌ Sudo only")
    if len(m.command) < 2:
        return await m.reply_text("📝 Usage: `/purge <query>`")
    try:
        query = m.text.split(None, 1)[1].strip().lower()
        result = await cache_col.delete_many({"query": {"$regex": query, "$options": "i"}})
        await m.reply_text(f"🗑️ Deleted {result.deleted_count} entries matching `{query}`")
    except Exception as e:
        await m.reply_text(f"❌ Error: {str(e)}")


@app.on_message(filters.command("teststorage"))
async def test_storage_handler(_, m: Message):
    if SUDOERS and m.from_user.id not in SUDOERS:
        return await m.reply_text("❌ Sudo only")

    msg = await m.reply_text("🔍 Testing storage...")
    try:
        storage_info = []
        if MUSIC_GROUP_ID:
            storage_info.append(f"Group: `{MUSIC_GROUP_ID}`")
        if MUSIC_CHANNEL_ID:
            storage_info.append(f"Channel: `{MUSIC_CHANNEL_ID}`")

        if not storage_info:
            return await msg.edit(
                "❌ No storage configured\n\nSet `MUSIC_GROUP_ID` or `MUSIC_CHANNEL_ID`"
            )

        await msg.edit(f"📡 Testing storage...\n\n{chr(10).join(storage_info)}")

        test_file = TEMP_DIR / "test_audio.ogg"
        test_thumb = TEMP_DIR / "test_thumb.jpg"

        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
            "-acodec", "libopus", "-b:a", "64k", str(test_file),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        if not test_file.exists():
            return await msg.edit("❌ Failed to create test file — is ffmpeg installed?")

        proc2 = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=black:100x100",
            "-frames:v", "1", str(test_thumb),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc2.communicate()

        sent = await upload_to_storage(
            str(test_file), "🎵 Test Audio", "Test Bot", 1,
            str(test_thumb) if test_thumb.exists() else None,
        )

        await msg.edit(
            f"✅ **Storage Test Successful!**\n\n"
            f"• File ID: `{sent.audio.file_id}`\n"
            f"• Storage: `{sent.chat.id}`\n"
            f"• Message ID: `{sent.id}`"
        )
        test_file.unlink(missing_ok=True)
        test_thumb.unlink(missing_ok=True)

    except Exception as e:
        await msg.edit(
            f"❌ **Test Failed**\n\n```{str(e)[:300]}```\n\n"
            "Ensure bot is admin with send permissions"
        )

# ==================== INLINE QUERIES ====================

@app.on_inline_query()
async def inline_query_handler(_, q: InlineQuery):
    query = q.query.strip()
    if not query:
        return await q.answer([], cache_time=1)
    try:
        matches = cache_col.find(
            {"query": {"$regex": query, "$options": "i"}}
        ).sort("created_at", -1).limit(5)
        results = []
        i = 0
        async for doc in matches:
            results.append(
                InlineQueryResultAudio(
                    id=str(i),
                    audio_file_id=doc["file_id"],
                    title=doc["title"],
                    performer=doc.get("performer", "Unknown"),
                )
            )
            i += 1
        await q.answer(results, cache_time=10)
    except Exception as e:
        print(f"[ERROR] Inline query: {e}")
        await q.answer([], cache_time=1)

# ==================== CLEANUP ====================

_shutdown_event = asyncio.Event()

def _handle_sigint():
    """Called on SIGINT/SIGTERM — cancels tasks so the loop can exit."""
    print("\n[SHUTDOWN] Signal received, cancelling tasks...")
    _shutdown_event.set()
    for task in asyncio.all_tasks():
        task.cancel()

async def cleanup():
    try:
        if 'arq' in globals() and arq is not None:
            if hasattr(arq, 'close'):
                await arq.close()
            elif hasattr(arq, 'session') and hasattr(arq.session, 'close'):
                await arq.session.close()
        if TEMP_DIR.exists():
            for d in TEMP_DIR.iterdir():
                if d.is_dir():
                    shutil.rmtree(d, ignore_errors=True)
        print("✅ Cleanup completed")
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")

def _register_cleanup():
    try:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handle_sigint)
            except (NotImplementedError, RuntimeError):
                pass
        if loop.is_running():
            loop.create_task(cleanup())
        else:
            loop.run_until_complete(cleanup())
    except Exception:
        pass

atexit.register(_register_cleanup)

# ==================== EXPORTS ====================

__all__ = [
    "download_audio",
    "upload_to_storage",
    "get_cached_song",
    "save_cached_song",
    "delete_cached_song",
    "cleanup",
]
