import json
import subprocess
import zipfile

import ffmpeg_manager as fm
from ffmpeg_manager import FFmpegManager


def test_get_local_version_parses(monkeypatch, tmp_path):
    ffmpeg_exe = tmp_path / "ffmpeg.exe"
    ffmpeg_exe.write_text("")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="ffmpeg version 7.1.0 Copyright (c) 2000-2025", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    manager = FFmpegManager(config_file=str(tmp_path / "config.json"))
    manager.ffmpeg_path = str(ffmpeg_exe)

    assert manager.get_local_version() == "7.1.0"


def test_get_local_version_none_se_mancante(tmp_path):
    manager = FFmpegManager(config_file=str(tmp_path / "config.json"))
    assert manager.get_local_version() is None


def test_set_ffmpeg_path_persiste(monkeypatch, tmp_path):
    ffmpeg_exe = tmp_path / "ffmpeg.exe"
    ffmpeg_exe.write_text("")
    config_file = tmp_path / "config.json"

    manager = FFmpegManager(config_file=str(config_file))
    assert manager.set_ffmpeg_path(str(ffmpeg_exe)) is True

    assert json.loads(config_file.read_text())["ffmpeg_path"] == str(ffmpeg_exe)

    manager2 = FFmpegManager(config_file=str(config_file))
    assert manager2.ffmpeg_path == str(ffmpeg_exe)


def test_set_ffmpeg_path_rifiuta_percorso_inesistente(tmp_path):
    manager = FFmpegManager(config_file=str(tmp_path / "config.json"))
    assert manager.set_ffmpeg_path(str(tmp_path / "inesistente.exe")) is False


def test_check_for_update(monkeypatch, tmp_path):
    manager = FFmpegManager(config_file=str(tmp_path / "config.json"))
    monkeypatch.setattr(manager, "get_local_version", lambda: "7.0.0")
    monkeypatch.setattr(manager, "get_remote_version", lambda: "7.1.0")

    info = manager.check_for_update()

    assert info["update_available"] is True
    assert info["local"] == "7.0.0"
    assert info["remote"] == "7.1.0"


def test_check_for_update_installa_se_mancante(monkeypatch, tmp_path):
    manager = FFmpegManager(config_file=str(tmp_path / "config.json"))
    manager.ffmpeg_path = str(tmp_path / "inesistente.exe")
    monkeypatch.setattr(manager, "get_local_version", lambda: None)
    monkeypatch.setattr(manager, "get_remote_version", lambda: "7.1.0")

    info = manager.check_for_update()

    assert info["update_available"] is True
    assert info["local"] is None
    assert info["remote"] == "7.1.0"


def test_check_for_update_confronto_numerico(monkeypatch, tmp_path):
    # "8.1.0" locale vs "8.1" remota: stessa versione, nessun aggiornamento
    manager = FFmpegManager(config_file=str(tmp_path / "config.json"))
    monkeypatch.setattr(manager, "get_local_version", lambda: "8.1.0")
    monkeypatch.setattr(manager, "get_remote_version", lambda: "8.1")

    assert manager.check_for_update()["update_available"] is False

    # Locale più nuova (10.0.0) rispetto alla remota (9.9.9): nessun aggiornamento
    monkeypatch.setattr(manager, "get_local_version", lambda: "10.0.0")
    monkeypatch.setattr(manager, "get_remote_version", lambda: "9.9.9")

    assert manager.check_for_update()["update_available"] is False


def test_check_for_update_build_master_non_promuove_install(monkeypatch, tmp_path):
    # Build master (es. "ffmpeg version N-124714-g49a77d37be") con versione non parsabile:
    # FFmpeg c'è, quindi nessun falso "installazione disponibile"
    ffmpeg_exe = tmp_path / "ffmpeg.exe"
    ffmpeg_exe.write_text("")
    manager = FFmpegManager(config_file=str(tmp_path / "config.json"))
    manager.ffmpeg_path = str(ffmpeg_exe)
    monkeypatch.setattr(manager, "get_local_version", lambda: None)
    monkeypatch.setattr(manager, "get_remote_version", lambda: "8.1")

    info = manager.check_for_update()

    assert info["update_available"] is False


def test_get_remote_version_estrae_la_piu_alta(monkeypatch, tmp_path):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"assets": [
                {"name": "ffmpeg-master-latest-win64-gpl-shared.zip"},
                {"name": "ffmpeg-n7.1-latest-win64-gpl-shared-7.1.zip"},
                {"name": "ffmpeg-n8.1-latest-win64-gpl-shared-8.1.zip"},
                {"name": "ffmpeg-master-latest-win64-gpl.zip"},
            ]}

    monkeypatch.setattr(fm.requests, "get", lambda *a, **k: FakeResponse())
    manager = FFmpegManager(config_file=str(tmp_path / "config.json"))

    assert manager.get_remote_version() == "8.1"


def test_version_tuple_ignora_suffissi_dev():
    assert fm.version_tuple("2026.07.04") == (2026, 7, 4)
    assert fm.version_tuple("2026.07.04.232701.dev.0") == (2026, 7, 4, 232701, 0)
    assert fm.version_tuple("8.1") == (8, 1, 0)
    assert fm.version_tuple("8.1.0") == (8, 1, 0)
    assert fm.version_tuple(None) == (0, 0, 0)
    assert fm.version_tuple("") == (0, 0, 0)


def test_version_tuple_uguale_con_componenti_mancanti():
    assert fm.version_tuple("8.1") == fm.version_tuple("8.1.0")
    assert fm.version_tuple("8.1") >= fm.version_tuple("8.1.0")
    assert not fm.version_tuple("8.1") < fm.version_tuple("8.1.0")
    assert fm.version_tuple("9.0") > fm.version_tuple("8.9.9")
    assert fm.version_tuple("2026.07.04.232701.dev.0") > fm.version_tuple("2026.07.04")


def test_check_for_update_nessuna_remota(monkeypatch, tmp_path):
    manager = FFmpegManager(config_file=str(tmp_path / "config.json"))
    monkeypatch.setattr(manager, "get_local_version", lambda: "7.0.0")
    monkeypatch.setattr(manager, "get_remote_version", lambda: None)

    info = manager.check_for_update()

    assert info["update_available"] is False


def test_download_and_install_estrae_bin(monkeypatch, tmp_path):
    zip_path = tmp_path / "ffmpeg.zip"
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("ffmpeg-master-latest-win64-gpl-shared/bin/ffmpeg.exe", b"BIN")
        zf.writestr("ffmpeg-master-latest-win64-gpl-shared/bin/avcodec-62.dll", b"DLL")

    def fake_download(url, target):
        with open(target, 'wb') as f:
            f.write(zip_path.read_bytes())

    manager = FFmpegManager(config_file=str(tmp_path / "config.json"))
    monkeypatch.setattr(manager, "_download_zip", fake_download)

    prog_dir = tmp_path / "app"
    prog_dir.mkdir()

    assert manager.download_and_install(str(prog_dir)) is True
    assert (prog_dir / "ffmpeg" / "bin" / "ffmpeg.exe").exists()
    assert (prog_dir / "ffmpeg" / "bin" / "avcodec-62.dll").exists()
    assert not (prog_dir / "ffmpeg.zip").exists()
    assert manager.ffmpeg_path == str(prog_dir / "ffmpeg" / "bin" / "ffmpeg.exe")


def test_download_and_install_pulisce_zip_corrotto(monkeypatch, tmp_path):
    def fake_download(url, target):
        with open(target, 'wb') as f:
            f.write(b"non e' uno zip")

    manager = FFmpegManager(config_file=str(tmp_path / "config.json"))
    monkeypatch.setattr(manager, "_download_zip", fake_download)

    prog_dir = tmp_path / "app"
    prog_dir.mkdir()

    assert manager.download_and_install(str(prog_dir)) is False
    assert not (prog_dir / "ffmpeg.zip").exists()
