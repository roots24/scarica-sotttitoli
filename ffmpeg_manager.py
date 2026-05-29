import os
import subprocess
import urllib.request
import zipfile
import shutil
import re
import json

class FFmpegManager:
    """
    Manages the installation, configuration, and versioning of FFmpeg binaries.
    Ensures that the application has a working FFmpeg executable for subtitle conversion.
    """
    def __init__(self, config_file="config.json"):
        self.config_file = config_file
        self.config = self._load_config()
        self.ffmpeg_path = self.config.get("ffmpeg_path")

    def _load_config(self):
        """Loads the FFmpeg path from a local JSON configuration file."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_config(self):
        """Persists the current FFmpeg configuration to the JSON file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Errore salvataggio config FFmpeg: {e}")

    def set_ffmpeg_path(self, path):
        """Updates the FFmpeg executable path and saves it to config."""
        if not path or not os.path.exists(path):
            return False
        self.ffmpeg_path = path
        self.config["ffmpeg_path"] = path
        self._save_config()
        return True

    def get_local_version(self):
        """ 
        Extracts the current FFmpeg version by executing 'ffmpeg -version'.
        Returns the version string (e.g., '7.1.0') or None if failed.
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

    def get_remote_version(self):
        """ 
        Fetches the latest FFmpeg release version from BtbN's GitHub API.
        This is used to notify the user if an update is available.
        """
        try:
            url = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
            with urllib.request.urlopen(url) as response:
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

    def check_for_update(self):
        """Compares local and remote versions to determine if an update is needed."""
        local = self.get_local_version()
        remote = self.get_remote_version()
        if local and remote and local != remote:
            return {"update_available": True, "local": local, "remote": remote}
        return {"update_available": False, "local": local, "remote": remote}

    def download_and_install(self, prog_dir=None):
        """ 
        Downloads the latest FFmpeg build from GitHub, extracts only the necessary 
        binaries (ffmpeg.exe and DLLs), and configures the path automatically.
        """
        if prog_dir is None:
            prog_dir = os.path.abspath(".")
            
        url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip"
        install_dir = os.path.join(prog_dir, "ffmpeg")
        os.makedirs(install_dir, exist_ok=True)
        zip_path = os.path.join(prog_dir, "ffmpeg.zip")

        try:
            urllib.request.urlretrieve(url, zip_path)
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

                if bin_folder:
                    target_bin_dir = os.path.join(install_dir, "bin")
                    os.makedirs(target_bin_dir, exist_ok=True)
                    for member in zip_ref.namelist():
                        if member.startswith(bin_folder):
                            filename = os.path.basename(member)
                            if filename:
                                source = zip_ref.open(member)
                                target = open(os.path.join(target_bin_dir, filename), 'wb')
                                shutil.copyfileobj(source, target)
                                target.close()
                                source.close()
                else:
                    raise Exception("Bin folder not found in zip")

            os.remove(zip_path)
            ffmpeg_exe = os.path.join(install_dir, "bin", "ffmpeg.exe")
            self.set_ffmpeg_path(ffmpeg_exe)
            return True
        except Exception as e:
            if os.path.exists(zip_path): os.remove(zip_path)
            print(f"FFmpeg installation error: {e}")
            return False

    def _get_default_path(self):
        """Returns the expected default path for FFmpeg relative to the application root."""
        return os.path.join(os.path.abspath("."), "ffmpeg", "bin", "ffmpeg.exe")
