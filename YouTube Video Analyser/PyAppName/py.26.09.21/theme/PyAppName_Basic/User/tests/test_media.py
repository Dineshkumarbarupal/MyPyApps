import pytest

from media_service import (
    clean_vtt,
    is_rate_limit_error,
    validate_youtube_url,
    _youtube_options,
)


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://youtube.com/shorts/dQw4w9WgXcQ",
    "https://www.youtube.com/embed/dQw4w9WgXcQ",
])
def test_valid_urls(url):
    assert validate_youtube_url(url) == "dQw4w9WgXcQ"


@pytest.mark.parametrize("url", [
    "http://youtube.com/watch?v=dQw4w9WgXcQ",
    "https://example.com/watch?v=dQw4w9WgXcQ",
    "javascript:alert(1)",
])
def test_reject_invalid_urls(url):
    with pytest.raises(ValueError):
        validate_youtube_url(url)


def test_vtt_parser_removes_timestamps_tags_and_duplicate_cues():
    source = (
        "WEBVTT\n\n00:00:00.0 --> 00:00:01.0\n<c>Hello</c>\n\n"
        "00:00:01.0 --> 00:00:02.0\nHello"
    )
    assert clean_vtt(source) == "Hello"


@pytest.mark.parametrize("message", [
    "HTTP Error 429: Too Many Requests",
    "server returned status code 429",
    "Too Many Requests",
])
def test_rate_limit_is_detected(message):
    assert is_rate_limit_error(RuntimeError(message))


def test_regular_download_error_is_not_a_rate_limit():
    assert not is_rate_limit_error(RuntimeError("Unable to extract video data"))


def test_cookie_options_require_explicit_supported_browser():
    assert "cookiesfrombrowser" not in _youtube_options("")
    assert _youtube_options("chrome")["cookiesfrombrowser"] == ("chrome",)
    assert _youtube_options("edge")["cookiesfrombrowser"] == ("edge",)
    assert "cookiesfrombrowser" not in _youtube_options("unsupported")
