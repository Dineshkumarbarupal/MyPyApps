import pytest
from media_service import validate_youtube_url,clean_vtt
@pytest.mark.parametrize("url",["https://www.youtube.com/watch?v=dQw4w9WgXcQ","https://youtu.be/dQw4w9WgXcQ","https://youtube.com/shorts/dQw4w9WgXcQ","https://www.youtube.com/embed/dQw4w9WgXcQ"])
def test_valid_urls(url):assert validate_youtube_url(url)=="dQw4w9WgXcQ"
@pytest.mark.parametrize("url",["http://youtube.com/watch?v=dQw4w9WgXcQ","https://example.com/watch?v=dQw4w9WgXcQ","javascript:alert(1)"])
def test_reject_invalid_urls(url):
    with pytest.raises(ValueError):validate_youtube_url(url)
def test_vtt_parser():
    assert clean_vtt("WEBVTT\n\n00:00:00.0 --> 00:00:01.0\n<c>Hello</c>\n\n00:00:01.0 --> 00:00:02.0\nHello")=="Hello"
