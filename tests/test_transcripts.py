import pytest
from unittest.mock import MagicMock, patch
from wrestling_logger.transcripts import fetch_transcripts, TranscriptResult, TranscriptLookupError
from yt_dlp.utils import DownloadError

@patch("wrestling_logger.transcripts.YoutubeDL")
def test_fetch_transcripts_success(mock_ytdl_cls):
    # Setup mock
    mock_ytdl = mock_ytdl_cls.return_value
    mock_ytdl.extract_info.return_value = {
        "requested_subtitles": {
            "en": {"url": "http://mock.url", "ext": "json3"}
        }
    }
    
    # Mock urlopen response for json3
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"events": [{"segs": [{"utf8": "Hello world"}]}]}'
    mock_ytdl.urlopen.return_value = mock_response

    results = fetch_transcripts(["video1"])
    
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].video_id == "video1"
    assert results[0].text == "Hello world"

@patch("wrestling_logger.transcripts.YoutubeDL")
def test_fetch_transcripts_download_error(mock_ytdl_cls):
    mock_ytdl = mock_ytdl_cls.return_value
    mock_ytdl.extract_info.side_effect = DownloadError("Mock download error")

    results = fetch_transcripts(["video1"])

    assert len(results) == 1
    assert results[0].success is False
    assert "Mock download error" in results[0].error

@patch("wrestling_logger.transcripts.YoutubeDL")
def test_fetch_transcripts_no_transcript(mock_ytdl_cls):
    mock_ytdl = mock_ytdl_cls.return_value
    # Return info but no subtitles
    mock_ytdl.extract_info.return_value = {"title": "Video"}

    results = fetch_transcripts(["video1"])

    assert len(results) == 1
    assert results[0].success is False
    assert "Transcript unavailable" in results[0].error
