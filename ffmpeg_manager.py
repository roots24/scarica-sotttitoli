import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from typing import Optional

CONFIG_FILE_NAME = "config.json"
FFMPEG_ZIP_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip"
GITHUB_API_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 60
CHUNK_SIZE = 1024 * 1024


def get_app_dir() -> str:
    """Restituisce la directory dell'app (script o eseguibile PyInstaller), indipendente dalla CWD."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class FFmpegManager:
    """Gestisce installazione, configurazione e versioni dei binari FFmpeg."""

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or os.path.join(get_app_dir(), CONFIG_FILE_NAME)
        self.config = self._load_config()
        self.ffmpeg_path: Optional[str] = self.config.get("ffmpeg_path")

    def _load_config(self) -> dict:
        """Carica il percorso FFmpeg dal file di configurazione JSON locale."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_config(self) -> None:
        """Persiste la configurazione FFmpeg corrente nel file JSON."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Errore salvataggio config FFmpeg: {e}")

    def set_ffmpeg_path(self, path: str) -> bool:
        """Aggiorna il percorso dell'eseguibile FFmpeg e lo salva nella configurazione."""
        if not path or not os.path.exists(path):
            return False
        self.ffmpeg_path = path
        self.config["ffmpeg_path"] = path
        self._save_config()
        return True

    def get_local_version(self) -> Optional[str]:
        """
        Estrae la versione FFmpeg locale eseguendo 'ffmpeg -version'.
        Restituisce la stringa di versione (es. '7.1.0') oppure None in caso di errore.
        """
        try:
            exe = self.ffmpeg_path or self._get_default_path()
            if not exe or not os.path.exists(exe):
                return None

            result = subprocess.run([exe, "-version"], capture_output=True, encoding='utf-8', errors='replace')
            match = re.search(r'ffmpeg version (\d+\.\d+\.\d+)', result.stdout)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    def get_remote_version(self) -> Optional[str]:
        """
        Recupera l'ultima versione FFmpeg dall'API GitHub di BtbN.
        Usata per notificare all'utente se è disponibile un aggiornamento.
        """
        try:
            url = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
            with urllib.request.urlopen(url, timeout=GITHUB_API_TIMEOUT) as response:
                data = json.loads(response.read().decode())
                assets = data.get("assets", [])
                for asset in assets:
                    name = asset.get("name", "")
                    if "win64-gpl-shared" in name:
                        match = re.search(r'ffmpeg-(\d+\.\d+\.\d+)', name)
                        if match:
                            return match.group(1)
        except Exception:
            pass
        return None

    def check_for_update(self) -> dict:
        """Confronta le versioni locale e remota per determinare se è disponibile un aggiornamento o un'installazione."""
        local = self.get_local_version()
        remote = self.get_remote_version()
        return {"update_available": bool(remote and (not local or local != remote)), "local": local, "remote": remote}

    def _download_zip(self, url: str, zip_path: str) -> None:
        """Scarica lo zip di FFmpeg con timeout, senza lasciare file parziali in caso di errore."""
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response:
            with open(zip_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file, CHUNK_SIZE)

    def download_and_install(self, prog_dir: Optional[str] = None) -> bool:
        """
        Scarica l'ultima build FFmpeg da GitHub, estrae solo i binari necessari
        (ffmpeg.exe e le DLL) e configura automaticamente il percorso.
        """
        if prog_dir is None:
            prog_dir = get_app_dir()

        install_dir = os.path.join(prog_dir, "ffmpeg")
        os.makedirs(install_dir, exist_ok=True)
        zip_path = os.path.join(prog_dir, "ffmpeg.zip")

        try:
            self._download_zip(FFMPEG_ZIP_URL, zip_path)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                bin_folder = None
                for member in zip_ref.namelist():
                    if 'bin/' in member and (member.split('/')[1] == 'bin' or member.startswith('bin/')):
                        bin_folder = '/'.join(member.split('/')[:-1]) + '/'
                        break

                if not bin_folder:
                    for member in zip_ref.namelist():
                        if member.endswith('ffmpeg.exe'):
                            bin_folder = os.path.dirname(member) + '/'
                            break

                if not bin_folder:
                    raise Exception("Cartella bin non trovata nello zip")

                target_bin_dir = os.path.join(install_dir, "bin")
                os.makedirs(target_bin_dir, exist_ok=True)
                for member in zip_ref.namelist():
                    if member.startswith(bin_folder):
                        filename = os.path.basename(member)
                        if filename:
                            with zip_ref.open(member) as source, open(os.path.join(target_bin_dir, filename), 'wb') as target:
                                shutil.copyfileobj(source, target)

            os.remove(zip_path)
            ffmpeg_exe = os.path.join(install_dir, "bin", "ffmpeg.exe")
            self.set_ffmpeg_path(ffmpeg_exe)
            return True
        except Exception as e:
            if os.path.exists(zip_path):
                os.remove(zip_path)
            print(f"Errore installazione FFmpeg: {e}")
            return False

    def _get_default_path(self) -> str:
        """Restituisce il percorso predefinito di FFmpeg rispetto alla directory dell'app."""
        return os.path.join(get_app_dir(), "ffmpeg", "bin", "ffmpeg.exe")
