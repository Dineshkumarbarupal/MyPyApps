from __future__ import annotations

import html
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from typing import Any, Callable

logger = logging.getLogger(__name__)
HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
SUPPORTED_COOKIE_BROWSERS = {"chrome", "edge", "firefox"}


def validate_youtube_url(value: str) -> str:
    parsed = urlparse((value or "").strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in HOSTS:
        raise ValueError("Only HTTPS YouTube video URLs are accepted.")
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    else:
        parts = [part for part in parsed.path.split("/") if part]
        video_id = parts[1] if len(parts) > 1 and parts[0] in {"shorts", "embed", "live"} else ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id or ""):
        raise ValueError("The URL does not contain a valid YouTube video ID.")
    return video_id


def clean_vtt(content: str) -> str:
    lines: list[str] = []
    previous = ""
    for raw in content.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line or line == "WEBVTT" or line.startswith(("NOTE", "STYLE", "REGION")):
            continue
        if "-->" in line or re.fullmatch(r"\d+", line):
            continue
        line = html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
        line = re.sub(r"\s+", " ", line)
        if line and line != previous:
            lines.append(line)
            previous = line
    return "\n".join(lines)


def is_rate_limit_error(error: BaseException) -> bool:
    message = str(error).lower()
    return "http error 429" in message or "too many requests" in message or "status code 429" in message


def find_ffmpeg_location() -> str | None:
    """Find FFmpeg from an explicit setting, PATH, or the imageio-ffmpeg package."""
    configured = os.getenv("YTA_FFMPEG_LOCATION", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file() or candidate.is_dir():
            return str(candidate.resolve())
        logger.warning("YTA_FFMPEG_LOCATION does not exist: %s", configured)

    system_binary = shutil.which("ffmpeg")
    if system_binary:
        return str(Path(system_binary).resolve())

    try:
        import imageio_ffmpeg
        bundled_binary = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if bundled_binary.is_file():
            return str(bundled_binary.resolve())
    except Exception as exc:
        logger.debug("Bundled FFmpeg is not available: %s", exc)
    return None


def ffmpeg_source() -> str:
    configured = os.getenv("YTA_FFMPEG_LOCATION", "").strip()
    if configured and Path(configured).exists():
        return "custom path"
    if shutil.which("ffmpeg"):
        return "system PATH"
    if find_ffmpeg_location():
        return "bundled (imageio-ffmpeg)"
    return "not found"


def _youtube_options(cookies_browser: str | None = None) -> dict[str, Any]:
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 2,
        "fragment_retries": 2,
        "extractor_retries": 1,
        "sleep_interval_requests": 1,
    }
    browser = (cookies_browser or "").strip().lower()
    if browser in SUPPORTED_COOKIE_BROWSERS:
        # Explicit user opt-in only: yt-dlp reads the selected local browser session.
        options["cookiesfrombrowser"] = (browser,)
    ffmpeg = find_ffmpeg_location()
    if ffmpeg:
        options["ffmpeg_location"] = ffmpeg
    return options


def _safe_title(title: str, video_id: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title or "youtube-video")
    return re.sub(r"\s+", " ", value).strip(" .")[:90] or video_id


def _whisper_transcript(url: str, progress: Callable[[float, str], None],
                        cookies_browser: str | None = None) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return ""

    import yt_dlp
    temporary = Path(tempfile.mkdtemp(prefix="yta-whisper-"))
    try:
        params = _youtube_options(cookies_browser)
        params.update({
            "format": "bestaudio/best",
            "outtmpl": str(temporary / "audio.%(ext)s"),
        })
        with yt_dlp.YoutubeDL(params) as ydl:
            ydl.download([url])
        audio_file = next((item for item in temporary.glob("audio.*") if item.is_file()), None)
        if not audio_file:
            return ""
        progress(8, "Transcribing audio locally")
        model = WhisperModel(os.getenv("YTA_WHISPER_MODEL", "small"), device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio_file), vad_filter=True)
        return "\n".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def process_video(
    url: str,
    options: dict[str, Any],
    output_dir: str,
    progress: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    import yt_dlp

    video_id = validate_youtube_url(url)
    progress = progress or (lambda percent, message: None)
    cookies_browser = options.get("cookies_browser")
    common = _youtube_options(cookies_browser)
    output_root = Path(output_dir).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    with yt_dlp.YoutubeDL({**common, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    title = info.get("title") or "YouTube video"
    job_dir = output_root / (_safe_title(title, video_id) + f" [{video_id}]")
    job_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, str]] = []
    warnings: list[str] = []
    ffmpeg = find_ffmpeg_location()

    def progress_hook(stage: str, base: float, span: float):
        def report(data: dict[str, Any]) -> None:
            if data.get("status") == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                downloaded = data.get("downloaded_bytes", 0)
                percent = min(99.0, downloaded / total * 100 if total else 0)
                progress(base + span * percent / 100, stage)
        return report

    if options.get("transcript"):
        progress(4, "Looking for captions")
        caption_dir = job_dir / "captions"
        caption_dir.mkdir(exist_ok=True)
        transcript = ""
        transcript_source = "YouTube captions"
        caption_error: Exception | None = None
        try:
            # Avoid wildcard language patterns: these can trigger extra translated-caption
            # requests and increase the chance of a YouTube subtitle rate limit.
            params = dict(common)
            params.update({
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["en", "hi"],
                "subtitlesformat": "vtt/best",
                "outtmpl": str(caption_dir / "caption.%(ext)s"),
                "sleep_interval_subtitles": 1,
            })
            with yt_dlp.YoutubeDL(params) as ydl:
                ydl.download([url])
            for subtitle_file in sorted(caption_dir.glob("*.vtt")):
                transcript = clean_vtt(subtitle_file.read_text(encoding="utf-8", errors="replace"))
                if transcript:
                    break
        except Exception as exc:
            caption_error = exc
            if is_rate_limit_error(exc):
                logger.warning("YouTube rate-limited subtitle requests for video %s (HTTP 429).", video_id)
                warnings.append(
                    "YouTube temporarily rate-limited caption requests (HTTP 429). "
                    "Wait before retrying, or open YouTube in your browser and resolve any challenge, "
                    "then opt in to that browser session below."
                )
            else:
                logger.warning("Caption extraction failed for %s: %s", video_id, exc)

        if not transcript and options.get("whisper_fallback", True):
            try:
                transcript = _whisper_transcript(url, progress, cookies_browser)
                if transcript:
                    transcript_source = "Faster-Whisper"
            except Exception as exc:
                if is_rate_limit_error(exc):
                    logger.warning("YouTube rate-limited the audio request used for local transcription (%s).", video_id)
                    warnings.append("Local transcription was also blocked by YouTube's temporary HTTP 429 rate limit.")
                else:
                    logger.warning("Local speech transcription could not complete for %s: %s", video_id, exc)

        if transcript:
            target = job_dir / "transcript.txt"
            target.write_text(
                f"Title: {title}\nVideo URL: {url}\nSource: {transcript_source}\n\n{transcript}\n",
                encoding="utf-8",
            )
            artifacts.append({"kind": "transcript", "path": str(target), "name": target.name})
        elif not caption_error or not is_rate_limit_error(caption_error):
            warnings.append("No usable captions were found. Install the optional Faster-Whisper package for local transcription.")

    if options.get("video"):
        try:
            progress(12, "Downloading video")
            params = dict(common)
            params.update({
                # Without FFmpeg, prefer a single-file stream (with audio) rather than
                # requesting separate video/audio streams that cannot be merged.
                "format": "bv*+ba/b" if ffmpeg else "best[ext=mp4]/best",
                "outtmpl": str(job_dir / "video.%(ext)s"),
                "progress_hooks": [progress_hook("Downloading video", 12, 80)],
                "continuedl": True,
            })
            if ffmpeg:
                params["merge_output_format"] = "mp4"
            else:
                warnings.append(
                    "FFmpeg was not found. Video is using a single-file fallback and may be lower quality. "
                    "Install the updated requirements for merged high-quality MP4 output."
                )
            with yt_dlp.YoutubeDL(params) as ydl:
                ydl.download([url])
            results = [
                item for item in job_dir.glob("video.*")
                if item.is_file() and item.suffix.lower() not in {".part", ".ytdl"}
            ]
            if results:
                selected = max(results, key=lambda item: item.stat().st_size)
                artifacts.append({"kind": "video", "path": str(selected), "name": selected.name})
            else:
                warnings.append("Video download did not produce a completed media file.")
        except Exception as exc:
            if is_rate_limit_error(exc):
                logger.warning("YouTube rate-limited video download for %s (HTTP 429).", video_id)
                warnings.append("YouTube temporarily rate-limited the video download (HTTP 429). Wait and retry later.")
            else:
                logger.exception("Video download failed for %s", video_id)
                warnings.append("Video download failed: " + str(exc))

    if options.get("audio"):
        try:
            if not ffmpeg:
                raise RuntimeError(
                    "FFmpeg is unavailable. Run 'python -m pip install -r requirements.txt' "
                    "to install the bundled FFmpeg helper, then restart the app."
                )
            progress(12, "Downloading and converting audio")
            params = dict(common)
            params.update({
                "format": "bestaudio/best",
                "outtmpl": str(job_dir / "audio.%(ext)s"),
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "progress_hooks": [progress_hook("Converting audio to MP3", 12, 80)],
                "continuedl": True,
            })
            with yt_dlp.YoutubeDL(params) as ydl:
                ydl.download([url])
            target = job_dir / "audio.mp3"
            if target.exists():
                artifacts.append({"kind": "audio", "path": str(target), "name": target.name})
            else:
                warnings.append("MP3 conversion completed without producing the expected audio.mp3 file.")
        except Exception as exc:
            if is_rate_limit_error(exc):
                logger.warning("YouTube rate-limited audio download for %s (HTTP 429).", video_id)
                warnings.append("YouTube temporarily rate-limited the audio download (HTTP 429). Wait and retry later.")
            else:
                logger.exception("Audio download failed for %s", video_id)
                warnings.append("Audio/MP3 download failed: " + str(exc))

    requested = sum(bool(options.get(key)) for key in ("transcript", "video", "audio"))
    status = "completed" if len(artifacts) >= requested else ("partial" if artifacts else "failed")
    progress(100 if status == "completed" else 98, "Completed" if status == "completed" else "Finished with warnings")
    return {"title": title, "status": status, "artifacts": artifacts, "warnings": warnings}
