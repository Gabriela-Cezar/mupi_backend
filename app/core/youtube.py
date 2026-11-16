"""Links do YouTube (PT-07): aceita só vídeos do YouTube e extrai o ID."""
import re
from urllib.parse import parse_qs, urlparse

_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

_HOSTS_YOUTUBE = {"youtube.com", "www.youtube.com", "m.youtube.com"}
_HOSTS_CURTOS = {"youtu.be", "www.youtu.be"}


def extract_youtube_id(url: str) -> str | None:
    """ID do vídeo, ou None se o link não for de um vídeo do YouTube.

    Formatos aceitos: youtube.com/watch?v=ID, youtu.be/ID e
    youtube.com/shorts/ID (com ou sem "www."/"m.", http ou https).
    """
    url = (url or "").strip()

    if not url:
        return None

    if "://" not in url:
        url = "https://" + url

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return None

    host = (parsed.hostname or "").lower()
    parts = [p for p in parsed.path.split("/") if p]

    candidate = None

    if host in _HOSTS_CURTOS and len(parts) == 1:
        candidate = parts[0]
    elif host in _HOSTS_YOUTUBE:
        if parts == ["watch"]:
            candidate = (parse_qs(parsed.query).get("v") or [None])[0]
        elif len(parts) == 2 and parts[0] == "shorts":
            candidate = parts[1]

    if candidate and _ID.match(candidate):
        return candidate

    return None


def watch_url(youtube_id: str) -> str:
    return f"https://www.youtube.com/watch?v={youtube_id}"
