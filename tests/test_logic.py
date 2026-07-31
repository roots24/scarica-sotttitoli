import os

import pytest
from yt_dlp.utils import DownloadError

import logic
from logic import (
    NetworkError,
    SubtitlesUnavailableError,
    VideoNotFoundError,
)


class FakeYDL:
    """Sostituisce yt_dlp.YoutubeDL nei test."""

    def __init__(self, dest):
        self.dest = dest
        self.opts = {}
        self.info = {"title": "Video Test"}
        self.extract_error = None
        self.saved_files = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def extract_info(self, url, download=False):
        if self.extract_error:
            raise self.extract_error
        if download:
            for filename in self.saved_files:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write("WEBVTT\n\n00:00.000 --> 00:05.000\nTesto\n")
        return self.info

    def prepare_filename(self, info):
        return os.path.join(self.dest, info["title"] + ".mp4")


def make_logic(tmp_path, monkeypatch, ydl=None):
    if ydl is None:
        ydl = FakeYDL(str(tmp_path))

    def replace(opts):
        ydl.opts = opts
        return ydl

    logic_instance = logic.SubtitleLogic()
    monkeypatch.setattr(logic.yt_dlp, "YoutubeDL", replace)
    monkeypatch.setattr(logic_instance, "ensure_dependencies", lambda: (True, None))
    monkeypatch.setattr(logic_instance.ffmpeg_mgr, "ffmpeg_path", "C:/fake/ffmpeg/bin/ffmpeg.exe")
    return logic_instance


def test_get_available_subtitles_merge_manual_e_auto(monkeypatch, tmp_path):
    ydl = FakeYDL(str(tmp_path))
    ydl.info = {
        'title': 'Video Test',
        'subtitles': {'it': [{'name': 'Italiano', 'ext': 'vtt'}]},
        'automatic_captions': {'en': [{'name': 'Inglese (auto)', 'ext': 'vtt'}]},
    }
    logic_instance = make_logic(tmp_path, monkeypatch, ydl)

    subs = logic_instance.get_available_subtitles("https://youtu.be/abc")

    assert len(subs) == 2
    assert {"lang": "it", "name": "Italiano", "type": "manual"} in subs
    assert {"lang": "en", "name": "Inglese (auto)", "type": "auto"} in subs


def test_get_available_subtitles_video_non_trovato(monkeypatch, tmp_path):
    ydl = FakeYDL(str(tmp_path))
    ydl.extract_error = DownloadError("Unable to extract initial data")
    logic_instance = make_logic(tmp_path, monkeypatch, ydl)

    with pytest.raises(VideoNotFoundError):
        logic_instance.get_available_subtitles("https://youtu.be/abc")


def test_get_available_subtitles_errore_rete(monkeypatch, tmp_path):
    ydl = FakeYDL(str(tmp_path))
    ydl.extract_error = DownloadError("request timed out")
    logic_instance = make_logic(tmp_path, monkeypatch, ydl)

    with pytest.raises(NetworkError):
        logic_instance.get_available_subtitles("https://youtu.be/abc")


def test_get_available_subtitles_retry_dopo_errore_rete(monkeypatch, tmp_path):
    calls = {"n": 0}
    real_fetch = logic.SubtitleLogic._fetch_available_subtitles

    def flaky(self, url):
        calls["n"] += 1
        if calls["n"] == 1:
            raise NetworkError("rete giù")
        return real_fetch(self, url)

    monkeypatch.setattr(logic.SubtitleLogic, "_fetch_available_subtitles", flaky)
    monkeypatch.setattr(logic.SubtitleLogic, "log", lambda self, msg: None)
    logic_instance = make_logic(tmp_path, monkeypatch)

    subs = logic_instance.get_available_subtitles("https://youtu.be/abc")

    assert calls["n"] == 2
    assert subs == []


def test_download_subtitles_srt_success(monkeypatch, tmp_path):
    ydl = FakeYDL(str(tmp_path))
    srt_file = os.path.join(str(tmp_path), "Video Test.en.srt")
    ydl.saved_files = [srt_file]
    logic_instance = make_logic(tmp_path, monkeypatch, ydl)

    result = logic_instance.download_subtitles(
        "https://youtu.be/abc", lang="en", dest=str(tmp_path), format="srt"
    )

    assert result == str(tmp_path)
    assert os.path.exists(srt_file)


def test_download_subtitles_usa_postprocessor_srt_e_txt(monkeypatch, tmp_path):
    for fmt in ("srt", "txt"):
        ydl = FakeYDL(str(tmp_path))
        ydl.saved_files = [os.path.join(str(tmp_path), f"Video Test.en.{fmt}.srt")]
        logic_instance = make_logic(tmp_path, monkeypatch, ydl)

        logic_instance.download_subtitles(
            "https://youtu.be/abc", lang="en", dest=str(tmp_path), format=fmt
        )

        assert ydl.opts["postprocessors"][0]["format"] == "srt"


def test_download_subtitles_sottotitoli_non_disponibili(monkeypatch, tmp_path):
    ydl = FakeYDL(str(tmp_path))
    ydl.saved_files = []
    logic_instance = make_logic(tmp_path, monkeypatch, ydl)

    with pytest.raises(SubtitlesUnavailableError):
        logic_instance.download_subtitles(
            "https://youtu.be/abc", lang="en", dest=str(tmp_path), format="srt"
        )


def test_download_subtitles_fallback_vtt_verso_srt(monkeypatch, tmp_path):
    vtt_file = os.path.join(str(tmp_path), "Video Test.en.vtt")

    def fake_convert(self, vtt_path):
        srt_path = os.path.splitext(vtt_path)[0] + ".srt"
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write("1\n00:00:00,000 --> 00:00:05,000\nTesto\n")
        os.remove(vtt_path)
        return True

    monkeypatch.setattr(logic.SubtitleLogic, "convert_vtt_to_srt", fake_convert)
    ydl = FakeYDL(str(tmp_path))
    ydl.saved_files = [vtt_file]
    logic_instance = make_logic(tmp_path, monkeypatch, ydl)

    result = logic_instance.download_subtitles(
        "https://youtu.be/abc", lang="en", dest=str(tmp_path), format="srt"
    )

    assert result == str(tmp_path)
    assert os.path.exists(os.path.join(str(tmp_path), "Video Test.en.srt"))


def test_download_subtitles_errore_rete(monkeypatch, tmp_path):
    ydl = FakeYDL(str(tmp_path))
    ydl.extract_error = DownloadError("HTTP Error 500")
    logic_instance = make_logic(tmp_path, monkeypatch, ydl)

    with pytest.raises(NetworkError):
        logic_instance.download_subtitles(
            "https://youtu.be/abc", lang="en", dest=str(tmp_path), format="srt"
        )


def test_download_subtitles_404_mappa_video_non_trovato(monkeypatch, tmp_path):
    ydl = FakeYDL(str(tmp_path))
    ydl.extract_error = DownloadError("HTTP Error 404: Not Found")
    logic_instance = make_logic(tmp_path, monkeypatch, ydl)

    with pytest.raises(VideoNotFoundError):
        logic_instance.download_subtitles(
            "https://youtu.be/abc", lang="en", dest=str(tmp_path), format="srt"
        )


def test_ensure_dependencies_solleva_dependency_error(monkeypatch, tmp_path):
    logic_instance = logic.SubtitleLogic()

    class StubFFmpeg:
        ffmpeg_path = None

        def _get_default_path(self):
            return os.path.join(str(tmp_path), "mancante", "ffmpeg.exe")

        def download_and_install(self, prog_dir):
            return False

    monkeypatch.setattr(logic_instance, "ffmpeg_mgr", StubFFmpeg())

    with pytest.raises(logic.DependencyError):
        logic_instance.download_subtitles(
            "https://youtu.be/abc", lang="en", dest=str(tmp_path), format="srt"
        )


def test_is_ytdlp_breakage():
    assert logic.is_ytdlp_breakage("Unable to extract JSON data")
    assert logic.is_ytdlp_breakage("errore in extract_info")
    assert not logic.is_ytdlp_breakage("sottotitoli non disponibili")
