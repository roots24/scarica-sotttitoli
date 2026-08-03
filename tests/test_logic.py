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
            auto_pass = self.opts.get("writeautomaticsub") is True and self.opts.get("writesubtitles") is False
            for filename in self.saved_files:
                is_auto_file = ".auto" in os.path.basename(filename)
                if auto_pass != is_auto_file:
                    continue
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write("WEBVTT\n\n00:00.000 --> 00:05.000\nTesto\n")
        return self.info

    def prepare_filename(self, info):
        outtmpl = str(self.opts.get("outtmpl", ""))
        suffix = ".auto" if ".auto" in outtmpl else ""
        return os.path.join(self.dest, info["title"] + suffix + ".mp4")


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
        dest = str(tmp_path / fmt)
        ydl = FakeYDL(dest)
        ydl.saved_files = [os.path.join(dest, "Video Test.en.srt")]
        logic_instance = make_logic(tmp_path, monkeypatch, ydl)

        logic_instance.download_subtitles(
            "https://youtu.be/abc", lang="en", dest=dest, format=fmt
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


def test_download_subtitles_entrambi_i_tipi_scarica_manual_e_auto(monkeypatch, tmp_path):
    ydl = FakeYDL(str(tmp_path))
    ydl.saved_files = [
        os.path.join(str(tmp_path), "Video Test.en.vtt"),
        os.path.join(str(tmp_path), "Video Test.auto.en.vtt"),
    ]

    def fake_convert(self, vtt_path):
        srt_path = os.path.splitext(vtt_path)[0] + ".srt"
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write("1\n00:00:00,000 --> 00:00:05,000\nTesto\n")
        os.remove(vtt_path)
        return True

    monkeypatch.setattr(logic.SubtitleLogic, "convert_vtt_to_srt", fake_convert)
    logic_instance = make_logic(tmp_path, monkeypatch, ydl)

    result = logic_instance.download_subtitles(
        "https://youtu.be/abc", lang="en", dest=str(tmp_path), format="srt"
    )

    assert result == str(tmp_path)
    assert os.path.exists(os.path.join(str(tmp_path), "Video Test.en.srt"))
    assert os.path.exists(os.path.join(str(tmp_path), "Video Test.auto.en.srt"))
    assert not os.path.exists(os.path.join(str(tmp_path), "Video Test.en.vtt"))
    assert not os.path.exists(os.path.join(str(tmp_path), "Video Test.auto.en.vtt"))


def test_download_subtitles_solo_automatici_senza_suffisso(monkeypatch, tmp_path):
    ydl = FakeYDL(str(tmp_path))
    ydl.saved_files = [os.path.join(str(tmp_path), "Video Test.en.vtt")]
    logic_instance = make_logic(tmp_path, monkeypatch, ydl)

    logic_instance.download_subtitles(
        "https://youtu.be/abc", lang="en", dest=str(tmp_path), format="vtt", manual_only=True
    )

    assert ".auto" not in str(ydl.opts["outtmpl"])


def test_js_runtimes_passato_con_chiave_node_e_path(monkeypatch, tmp_path):
    ydl = FakeYDL(str(tmp_path))
    ydl.saved_files = [os.path.join(str(tmp_path), "Video Test.en.srt")]
    logic_instance = make_logic(tmp_path, monkeypatch, ydl)
    monkeypatch.setattr(logic_instance, "ensure_dependencies", lambda: (True, "C:/node/node.exe"))

    logic_instance.download_subtitles(
        "https://youtu.be/abc", lang="en", dest=str(tmp_path), format="srt"
    )

    assert ydl.opts["js_runtimes"] == {"node": {"path": "C:/node/node.exe"}}


def test_convert_srt_to_txt_rimuove_indici_e_timestamp(tmp_path):
    srt_file = os.path.join(str(tmp_path), "Video.en.srt")
    with open(srt_file, 'w', encoding='utf-8') as f:
        f.write("1\n00:00:00,000 --> 00:00:05,000\nCiao mondo\n\n2\n00:00:05,000 --> 00:00:09,000\nSeconda riga\n")

    logic_instance = logic.SubtitleLogic()
    assert logic_instance.convert_srt_to_txt(srt_file) is True

    txt_file = os.path.join(str(tmp_path), "Video.en.txt")
    assert os.path.exists(txt_file)
    assert not os.path.exists(srt_file)
    content = open(txt_file, encoding='utf-8').read()
    assert "Ciao mondo" in content
    assert "Seconda riga" in content
    assert "-->" not in content


def test_convert_srt_to_txt_fallisce_senza_testo(tmp_path):
    srt_file = os.path.join(str(tmp_path), "Video.en.srt")
    with open(srt_file, 'w', encoding='utf-8') as f:
        f.write("1\n00:00:00,000 --> 00:00:05,000\n")

    logic_instance = logic.SubtitleLogic()
    assert logic_instance.convert_srt_to_txt(srt_file) is False
    assert os.path.exists(srt_file)


def test_download_subtitles_ignora_file_stantii_in_destinazione(monkeypatch, tmp_path):
    # Un file .srt lasciato da un download precedente non deve contare come successo
    stale_file = os.path.join(str(tmp_path), "Video Test.en.srt")
    with open(stale_file, 'w', encoding='utf-8') as f:
        f.write("srt stantio")
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


def test_is_ytdlp_breakage_nessun_falso_positivo():
    assert not logic.is_ytdlp_breakage("Errore di rete: timeout dopo 15 secondi")
    assert not logic.is_ytdlp_breakage("Unsupported protocol: ftp")
    assert not logic.is_ytdlp_breakage("Sottotitoli non trovati per la lingua en")


def test_download_subtitles_playlist_scarica_tutti_gli_entries(monkeypatch, tmp_path):
    ydl = FakeYDL(str(tmp_path))
    ydl.info = {
        '_type': 'playlist',
        'title': 'Playlist Test',
        'entries': [{'title': 'Video 1'}, {'title': 'Video 2'}],
    }
    ydl.saved_files = [
        os.path.join(str(tmp_path), "Video 1.en.srt"),
        os.path.join(str(tmp_path), "Video 2.en.srt"),
    ]
    logic_instance = make_logic(tmp_path, monkeypatch, ydl)

    result = logic_instance.download_subtitles(
        "https://youtu.be/abc?list=PLtest", lang="en", dest=str(tmp_path), format="srt"
    )

    assert result == str(tmp_path)


def test_download_subtitles_playlist_manca_un_file_ma_continua(monkeypatch, tmp_path):
    ydl = FakeYDL(str(tmp_path))
    ydl.info = {
        '_type': 'playlist',
        'title': 'Playlist Test',
        'entries': [{'title': 'Video 1'}, {'title': 'Video 2'}],
    }
    ydl.saved_files = [os.path.join(str(tmp_path), "Video 1.en.srt")]
    logic_instance = make_logic(tmp_path, monkeypatch, ydl)

    result = logic_instance.download_subtitles(
        "https://youtu.be/abc?list=PLtest", lang="en", dest=str(tmp_path), format="srt"
    )

    assert result == str(tmp_path)
    assert not os.path.exists(os.path.join(str(tmp_path), "Video 2.en.srt"))


def test_download_subtitles_playlist_nessun_file_solleva_errore(monkeypatch, tmp_path):
    ydl = FakeYDL(str(tmp_path))
    ydl.info = {
        '_type': 'playlist',
        'title': 'Playlist Test',
        'entries': [{'title': 'Video 1'}, {'title': 'Video 2'}],
    }
    ydl.saved_files = []
    logic_instance = make_logic(tmp_path, monkeypatch, ydl)

    with pytest.raises(SubtitlesUnavailableError):
        logic_instance.download_subtitles(
            "https://youtu.be/abc?list=PLtest", lang="en", dest=str(tmp_path), format="srt"
        )


def test_download_queue_conta_successi_e_errori(monkeypatch, tmp_path):
    logic_instance = make_logic(tmp_path, monkeypatch)

    def fake_download(url, **kwargs):
        if url == "https://youtu.be/ok":
            return "/dest"
        raise VideoNotFoundError("Video non trovato")

    monkeypatch.setattr(logic_instance, "download_subtitles", fake_download)
    monkeypatch.setattr(logic_instance, "log", lambda msg: None)

    result = logic_instance.download_queue(
        ["https://youtu.be/ok", "https://youtu.be/bad"], lang="en", dest=str(tmp_path)
    )

    assert result == {"successi": 1, "errori": 1}


def test_download_queue_logga_errori_senza_bloccare_la_coda(monkeypatch, tmp_path):
    logic_instance = make_logic(tmp_path, monkeypatch)
    log_messages = []

    def fake_download(url, **kwargs):
        raise SubtitlesUnavailableError("lingua non disponibile")

    monkeypatch.setattr(logic_instance, "download_subtitles", fake_download)
    monkeypatch.setattr(logic_instance, "log", lambda msg: log_messages.append(msg))

    result = logic_instance.download_queue(
        ["https://youtu.be/a", "https://youtu.be/b"], lang="xx", dest=str(tmp_path)
    )

    assert result == {"successi": 0, "errori": 2}
    assert any("Errore per" in msg for msg in log_messages)


def test_with_retry_usa_retry_configurabile(monkeypatch, tmp_path):
    from config import AppConfig
    from logic import SubtitleLogic

    app_config = AppConfig(config_file=str(tmp_path / "config.json"))
    app_config.retry_attempts = 3
    app_config.retry_delay = 0.01
    logic_instance = SubtitleLogic(app_config=app_config)
    monkeypatch.setattr(logic_instance, "log", lambda msg: None)

    calls = {"n": 0}

    def sempre_rete_giu():
        calls["n"] += 1
        raise NetworkError("rete giù")

    with pytest.raises(NetworkError):
        logic_instance._with_retry(sempre_rete_giu)

    assert calls["n"] == 3


def test_subtitle_logic_accetta_ffmpeg_mgr_condiviso():
    from ffmpeg_manager import FFmpegManager
    from logic import SubtitleLogic

    manager = FFmpegManager(config_file="C:/percorso/config.json")
    logic_instance = SubtitleLogic(ffmpeg_mgr=manager)

    assert logic_instance.ffmpeg_mgr is manager
