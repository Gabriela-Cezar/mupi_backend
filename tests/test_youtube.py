"""Links de vídeo: só YouTube, guardando o ID (PT-07)."""
import pytest

from app.core.youtube import extract_youtube_id, watch_url

ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize("link", [
    f"https://www.youtube.com/watch?v={ID}",
    f"https://youtube.com/watch?v={ID}",
    f"https://m.youtube.com/watch?v={ID}",
    f"http://www.youtube.com/watch?v={ID}",
    f"https://www.youtube.com/watch?v={ID}&t=42s",
    f"https://www.youtube.com/watch?feature=share&v={ID}",
    f"https://youtu.be/{ID}",
    f"https://youtu.be/{ID}?si=abc123",
    f"https://www.youtube.com/shorts/{ID}",
    f"youtu.be/{ID}",
    f"  https://youtu.be/{ID}  ",
])
def test_links_aceitos(link):
    assert extract_youtube_id(link) == ID


@pytest.mark.parametrize("link", [
    "",
    None,
    "https://vimeo.com/123456",
    f"https://example.com/watch?v={ID}",
    f"https://youtube.com.golpe.com/watch?v={ID}",
    "https://www.youtube.com/watch",
    "https://www.youtube.com/watch?v=curto",
    "https://www.youtube.com/channel/UC1234567890",
    "https://www.youtube.com/playlist?list=PL123",
    f"ftp://youtu.be/{ID}",
    f"https://youtu.be/{ID}/extra",
    "javascript:alert(1)",
])
def test_links_recusados(link):
    assert extract_youtube_id(link) is None


def test_watch_url():
    assert watch_url(ID) == f"https://www.youtube.com/watch?v={ID}"
