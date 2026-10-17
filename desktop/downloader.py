import re
from pathlib import Path
from urllib.parse import urlparse


DOWNLOAD_DIR = Path(
    __import__("os").environ.get(
        "LEONTV_DOWNLOAD_DIR", str(Path.home() / "Downloads" / "LeonTV-Downloader")
    )
).expanduser()
SUPPORTED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "twitch.tv",
    "www.twitch.tv",
    "m.twitch.tv",
}
TIMESTAMP_PATTERN = re.compile(r"^(?:(\d{1,3}):)?([0-5]?\d):([0-5]?\d)$")


def validate_video_url(url):
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in SUPPORTED_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Bitte eine gültige YouTube- oder Twitch-Video-URL eingeben.")
    if parsed.hostname in {"twitch.tv", "www.twitch.tv", "m.twitch.tv"}:
        if not re.match(r"^/videos/\d+/?$", parsed.path):
            raise ValueError("Unterstützt werden Twitch-VODs unter /videos/…")
    elif parsed.hostname in {"youtu.be", "www.youtu.be"}:
        if not parsed.path.strip("/"):
            raise ValueError("Die URL enthält keine YouTube-Video-ID.")
    elif not (
        parsed.path == "/watch" and bool(__import__("urllib.parse", fromlist=["parse_qs"]).parse_qs(parsed.query).get("v"))
        or re.match(r"^/(?:shorts|live|embed)/[^/]+/?$", parsed.path)
    ):
        raise ValueError("Die URL enthält kein unterstütztes YouTube-Video.")
    return url


def parse_timestamp(value):
    match = TIMESTAMP_PATTERN.fullmatch(value.strip()) if isinstance(value, str) else None
    if not match:
        raise ValueError("Zeitangaben müssen MM:SS oder HH:MM:SS sein.")
    hours, minutes, seconds = match.groups()
    return (int(hours or 0) * 3600) + (int(minutes) * 60) + int(seconds)


def parse_clip_range(start, end, duration=None):
    if not start and not end:
        return None
    if not start or not end:
        raise ValueError("Bitte Start- und Endzeit für den Twitch-Ausschnitt eingeben.")
    start_seconds = parse_timestamp(start)
    end_seconds = parse_timestamp(end)
    if start_seconds >= end_seconds:
        raise ValueError("Die Endzeit muss nach der Startzeit liegen.")
    if duration and end_seconds > duration:
        raise ValueError("Die Endzeit liegt hinter dem Ende des Videos.")
    return start_seconds, end_seconds


def _format_size(size):
    return round(size / (1024 * 1024), 1) if size else None


def _yt_dlp_options():
    options = {"quiet": True, "no_warnings": True, "noplaylist": True}
    ffmpeg_location = __import__("os").environ.get("FFMPEG_LOCATION")
    if ffmpeg_location:
        options["ffmpeg_location"] = ffmpeg_location
    return options


def get_video_info(url):
    import yt_dlp

    validate_video_url(url)
    with yt_dlp.YoutubeDL(_yt_dlp_options()) as ydl:
        info = ydl.extract_info(url, download=False)
    duration = info.get("duration")
    video_formats = [
        item
        for item in info.get("formats", [])
        if item.get("height") and item.get("vcodec") != "none"
    ]
    audio_formats = [
        item for item in info.get("formats", []) if item.get("acodec") != "none"
    ]
    best_audio_size = max(
        (item.get("filesize") or item.get("filesize_approx") or 0 for item in audio_formats),
        default=0,
    )
    qualities = []
    for height in sorted({item["height"] for item in video_formats}, reverse=True):
        candidates = [item for item in video_formats if item["height"] == height]
        selected = max(
            candidates,
            key=lambda item: item.get("filesize") or item.get("filesize_approx") or 0,
        )
        size = (selected.get("filesize") or selected.get("filesize_approx") or 0)
        if selected.get("acodec") == "none":
            size += best_audio_size
        size_mb = _format_size(size)
        qualities.append(
            {
                "value": str(height),
                "label": f"{height}p" + (f" · ca. {size_mb} MB" if size_mb else ""),
                "size_mb": size_mb,
            }
        )
    if not qualities:
        qualities.append({"value": "best", "label": "Beste verfügbare Qualität", "size_mb": None})
    mp3_size = round(duration * 192_000 / 8 / (1024 * 1024), 1) if duration else None
    if info.get("is_live"):
        raise ValueError("Live-Streams werden nicht unterstützt; bitte ein VOD öffnen.")
    return {
        "title": info.get("title") or "Unbekanntes Video",
        "duration": duration,
        "thumbnail": info.get("thumbnail"),
        "qualities": qualities,
        "mp3_size_mb": mp3_size,
    }


def build_download_options(request, video_info, on_progress):
    media_format = request["format"]
    if media_format not in {"mp4", "mp3"}:
        raise ValueError("Das Ausgabeformat muss MP4 oder MP3 sein.")
    options = {
        **_yt_dlp_options(),
        "outtmpl": str(DOWNLOAD_DIR / "%(title).180B [%(id)s].%(ext)s"),
        "progress_hooks": [on_progress],
        "noplaylist": True,
    }
    if media_format == "mp3":
        options.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }
        )
    else:
        quality = request.get("quality") or "best"
        if quality != "best" and (not quality.isdigit() or int(quality) > 4320):
            raise ValueError("Ungültige Videoqualität.")
        limit = f"[height<={quality}]" if quality != "best" else ""
        options.update(
            {
                "format": (
                    f"bestvideo{limit}[ext=mp4]+bestaudio[ext=m4a]/"
                    f"best{limit}[ext=mp4]/best{limit}"
                ),
                "merge_output_format": "mp4",
            }
        )
    if request.get("start") or request.get("end"):
        if "twitch.tv" not in urlparse(request["url"]).hostname:
            raise ValueError("Ausschnitte sind nur für Twitch-VODs verfügbar.")
        clip = parse_clip_range(
            request.get("start", ""), request.get("end", ""), video_info.get("duration")
        )
        options.update(
            {
                "download_sections": [f"*{clip[0]}-{clip[1]}"],
                "force_keyframes_at_cuts": True,
            }
        )
    return options


def download_video(request, video_info, on_progress):
    import yt_dlp

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    options = build_download_options(request, video_info, on_progress)
    with yt_dlp.YoutubeDL(options) as ydl:
        result = ydl.extract_info(request["url"], download=True)
        return result.get("_filename") or ydl.prepare_filename(result)
