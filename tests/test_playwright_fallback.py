import os
import pytest
from unittest import mock

from dialogue_finder.downloader import download_video, DownloadError
from dialogue_finder.pipeline import run_pipeline
from dialogue_finder import config
from dialogue_finder.models import FinderResult


@mock.patch("dialogue_finder.downloader.yt_dlp.YoutubeDL")
@mock.patch("dialogue_finder.downloader._playwright_download_fallback")
def test_playwright_fallback_is_called_for_okru(mock_playwright, mock_ytdl, tmp_path):
    """
    Test that if yt-dlp fails for an ok.ru URL, the Playwright fallback is attempted.
    """
    # Mock yt-dlp to raise DownloadError (it fails to download)
    mock_instance = mock.MagicMock()
    mock_instance.__enter__.return_value = mock_instance
    mock_instance.download.return_value = 1  # 1 indicates error in yt-dlp
    mock_ytdl.return_value = mock_instance
    
    # Mock playwright to simulate success
    mock_playwright.return_value = os.path.join(tmp_path, "video.mp4")

    url = "https://ok.ru/video/12345"
    
    # Execute
    result = download_video(url, str(tmp_path))
    
    # Verify Playwright was called
    mock_playwright.assert_called_once_with(url, str(tmp_path))
    assert result == os.path.join(tmp_path, "video.mp4")


@mock.patch("dialogue_finder.downloader.yt_dlp.YoutubeDL")
@mock.patch("dialogue_finder.downloader._playwright_download_fallback")
def test_playwright_fallback_failure_raises_download_error(mock_playwright, mock_ytdl, tmp_path):
    """
    Test that if BOTH yt-dlp and Playwright fail, a DownloadError is raised
    with a clear message about TLS/IP blocking.
    """
    # Mock yt-dlp to fail
    mock_instance = mock.MagicMock()
    mock_instance.__enter__.return_value = mock_instance
    mock_instance.download.return_value = 1
    mock_ytdl.return_value = mock_instance
    
    # Mock playwright to also fail
    mock_playwright.side_effect = RuntimeError("Playwright mock failure")

    url = "https://ok.ru/video/12345"
    
    # Execute and verify exception
    with pytest.raises(DownloadError) as exc_info:
        download_video(url, str(tmp_path))
    
    # Verify the specific error message includes TLS/IP block details
    assert "TLS fingerprint or IP block" in str(exc_info.value)
    assert "Playwright fallback error" in str(exc_info.value)


@mock.patch("dialogue_finder.pipeline.download_video")
@mock.patch("dialogue_finder.pipeline.get_video_info")
@mock.patch("dialogue_finder.pipeline.extract_audio")
@mock.patch("dialogue_finder.pipeline.transcribe")
@mock.patch("dialogue_finder.pipeline.find_asr_window")
@mock.patch("dialogue_finder.pipeline.search_frames")
def test_pipeline_cleanup_on_success(
    mock_search, mock_asr_win, mock_transcribe, mock_audio, mock_vid_info, mock_download, tmp_path
):
    """
    Test that run_pipeline correctly deletes the temporary work_dir upon success.
    """
    # Mock dependencies to simulate a successful pipeline run
    mock_download.return_value = "/fake/video.mp4"
    
    mock_info = mock.MagicMock()
    mock_info.duration_sec = 10.0
    mock_vid_info.return_value = mock_info
    
    mock_asr_win.return_value = mock.MagicMock()
    
    mock_candidate = mock.MagicMock()
    mock_candidate.frame_number = 1
    mock_candidate.match_score = 95.0
    mock_candidate.persists = True
    mock_search.return_value = mock_candidate
    
    # Mock the extract/save frame part to do nothing
    with mock.patch("dialogue_finder.pipeline.extract_frame"), mock.patch("dialogue_finder.pipeline.save_frame"):
        
        # We need to capture the auto-generated work_dir. We can do this by wrapping tempfile.mkdtemp
        with mock.patch("tempfile.mkdtemp") as mock_mkdtemp:
            fake_work_dir = os.path.join(tmp_path, "dff_work_fake")
            os.makedirs(fake_work_dir)
            mock_mkdtemp.return_value = fake_work_dir
            
            # Execute pipeline without providing work_dir (so it auto-creates and cleans up)
            run_pipeline("http://fake.url", "target text", output_dir=str(tmp_path))
            
            # Verify cleanup
            assert not os.path.exists(fake_work_dir), "Temporary directory was not deleted!"


@mock.patch("dialogue_finder.pipeline.download_video")
def test_pipeline_cleanup_on_failure(mock_download, tmp_path):
    """
    Test that run_pipeline correctly deletes the temporary work_dir even if a stage fails.
    """
    # Force the very first stage to fail
    mock_download.side_effect = DownloadError("Forced failure")
    
    with mock.patch("tempfile.mkdtemp") as mock_mkdtemp:
        fake_work_dir = os.path.join(tmp_path, "dff_work_fake")
        os.makedirs(fake_work_dir)
        mock_mkdtemp.return_value = fake_work_dir
        
        # Execute pipeline - it should raise the error
        with pytest.raises(DownloadError):
            run_pipeline("http://fake.url", "target text", output_dir=str(tmp_path))
        
        # Verify cleanup STILL happened despite the exception
        assert not os.path.exists(fake_work_dir), "Temporary directory was not deleted on failure!"
