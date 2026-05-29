import yt_dlp
import os
import subprocess
import shutil
import sys
import urllib.request
import zipfile
from ffmpeg_manager import FFmpegManager

# --- Custom Exceptions ---
class SubtitleError(Exception):
    """Base exception for subtitle downloader"""
    pass

class VideoNotFoundError(SubtitleError):
    """Raised when the video cannot be found"""
    pass

class SubtitlesUnavailableError(SubtitleError):
    """Raised when subtitles are not available in the requested language"""
    pass

class NetworkError(SubtitleError):
    """Raised during network-related failures"""
    pass

class DependencyError(SubtitleError):
    """Raised when ffmpeg or nodejs is missing and cannot be installed"""
    pass

# --- Utilities ---
def get_program_dir():
    """Returns the directory where the current script or executable is located."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(".")

def get_resource_path(relative_path):
    """Returns the absolute path to a resource, supporting both development and PyInstaller environments."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = get_program_dir()
    return os.path.join(base_path, relative_path)

# --- Core Logic ---
class SubtitleLogic:
    def __init__(self, logger=None):
        self.logger = logger
        self.ffmpeg_mgr = FFmpegManager()

    def log(self, msg):
        if self.logger and hasattr(self.logger, 'log'):
            self.logger.log(msg)
        else:
            print(msg)

    def ensure_dependencies(self):
        """Verifies if FFmpeg and Node.js are installed, attempting to install them if they are missing."""
        ffmpeg_exists = os.path.exists(self.ffmpeg_mgr.ffmpeg_path or self.ffmpeg_mgr._get_default_path())

        if not ffmpeg_exists:
            self.log("FFmpeg non trovato. Tentativo di installazione...")
            if not self.ffmpeg_mgr.download_and_install(get_program_dir()):
                raise DependencyError("Impossibile scaricare FFmpeg. È necessario per la conversione in .srt")
            ffmpeg_exists = True

        node_path = None
        try:
            result = subprocess.run(["where", "node"], capture_output=True, encoding='utf-8', errors='replace', check=True)
            node_path = result.stdout.strip().split('\n')[0]
            self.log(f"JS Runtime trovato: {node_path}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.log("JS Runtime (Node.js) non trovato. Tentativo di installazione...")
            try:
                subprocess.run(["choco", "install", "nodejs", "-y"], check=True, capture_output=True)
                possible_paths = [
                    r"C:\Program Files\nodejs\node.exe",
                    r"C:\Program Files (x86)\nodejs\node.exe",
                    os.path.join(os.environ.get('LocalAppData', ''), 'bin', 'node.exe')
                ]
                for p in possible_paths:
                    if os.path.exists(p):
                        node_path = p
                        self.log(f"JS Runtime installato e trovato in: {node_path}")
                        break
            except Exception as e:
                self.log(f"Impossibile installare Node.js automaticamente: {e}")

        return ffmpeg_exists, node_path

    def get_available_subtitles(self, url):
        """Retrieves the list of available subtitles (manual and automatic) for a specified video URL."""
        ydl_opts = {'skip_download': True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                subs = info.get('subtitles', {})
                auto_subs = info.get('automatic_captions', {})
                
                available = []
                # Manual subtitles
                for lang, data in subs.items():
                    available.append({'lang': lang, 'name': data[0].get('name', lang), 'type': 'manual'})
                
                # Automatic subtitles
                for lang, data in auto_subs.items():
                    available.append({'lang': lang, 'name': data[0].get('name', lang), 'type': 'auto'})
                
                return available
        except yt_dlp.utils.DownloadError as e:
            if "404" in str(e) or "Unable to extract" in str(e):
                raise VideoNotFoundError(f"Video non trovato o non accessibile: {url}")
            raise NetworkError(f"Errore di rete durante l'estrazione dei dati: {e}")
        except Exception as e:
            raise SubtitleError(f"Errore imprevisto nell'estrazione delle lingue: {e}")

    def convert_vtt_to_srt(self, vtt_path):
        srt_path = os.path.splitext(vtt_path)[0] + ".srt"
        try:
            ffmpeg_exe = self.ffmpeg_mgr.ffmpeg_path or self.ffmpeg_mgr._get_default_path()
            if not os.path.exists(ffmpeg_exe):
                raise DependencyError(f"FFmpeg non trovato in {ffmpeg_exe}")
 
            cmd = [ffmpeg_exe, "-y", "-i", vtt_path, srt_path]

            result = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace')
            if result.returncode != 0:
                self.log(f"Errore FFmpeg nella conversione: {result.stderr}")
                return False
            
            if os.path.exists(vtt_path):
                os.remove(vtt_path)
            return True
        except Exception as e:
            self.log(f"Errore critico durante la conversione: {e}")
            return False

    def download_subtitles(self, url, lang, dest, format='srt', auto_only=False, manual_only=False, progress_hook=None):
        """
        Downloads subtitles for a given video URL in the specified language and format.

        Args:
            url (str): The URL of the video.
            lang (str): The language code for the subtitles.
            dest (str): Destination directory to save the file.
            format (str): Subtitle format ('srt', 'vtt', or 'txt'). Defaults to 'srt'.
            auto_only (bool): If True, only attempts to download automatic captions.
            manual_only (bool): If True, only attempts to download manual subtitles.
            progress_hook (callable): Optional callback function for tracking progress.

        Returns:
            str: The absolute path to the destination directory if successful.
        """
        try:
            ffmpeg_ok, node_path = self.ensure_dependencies()
            if not ffmpeg_ok:
                raise DependencyError("FFmpeg non disponibile.")

            if node_path:
                node_dir = os.path.dirname(node_path)
                if node_dir not in os.environ['PATH']:
                    os.environ['PATH'] = node_dir + os.pathsep + os.environ['PATH']

            if not os.path.exists(dest):
                os.makedirs(dest)

            ffmpeg_abs_path = os.path.dirname(self.ffmpeg_mgr.ffmpeg_path or self.ffmpeg_mgr._get_default_path())
            
            # Configure subtitle filters based on manual/automatic preferences
            
            ydl_opts = {
                'writesubtitles': not auto_only,
                'writeautomaticsub': not manual_only,
                'subtitleslangs': [lang],
                'skip_download': True,
                'outtmpl': os.path.join(dest, '%(title)s.%(ext)s'),
                'ffmpeg_location': ffmpeg_abs_path, 
                'logger': self._create_logger(),
                'progress_hooks': [progress_hook] if progress_hook else [],
            }

            # Format handling: yt-dlp can convert to srt via postprocessor
            if format == 'srt':
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegSubtitlesConvertor',
                    'format': 'srt',
                }]
            elif format == 'vtt':
                # Default is vtt, so no postprocessor needed usually
                pass 
            elif format == 'txt':
                # TXT conversion is not directly supported by yt-dlp; we use SRT as a baseline.
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegSubtitlesConvertor',
                    'format': 'srt',
                }]

            if node_path:
                ydl_opts['js_runtimes'] = {'Node': {'executable': node_path}}

            self.log(f"Avvio download sottotitoli ({lang}) per: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True) # Need download=True to actually run the process
                filename = ydl.prepare_filename(info)
                
                # Fallback conversion for those that didn't get converted by postprocessor
                video_title_slug = os.path.splitext(os.path.basename(filename))[0]
                for f in os.listdir(dest):
                    if f.endswith(".vtt") and video_title_slug in f and format == 'srt':
                        self.log(f"Conversione manuale di {f} -> .srt...")
                        self.convert_vtt_to_srt(os.path.join(dest, f))

                # Final check
                found = False
                ext = ".srt" if format == 'srt' else ".vtt"
                for f in os.listdir(dest):
                    if f.endswith(ext) and video_title_slug in f:
                        found = True
                        break
                
                if not found:
                    raise SubtitlesUnavailableError(f"Sottotitoli non trovati per la lingua {lang}")

            self.log(f"Operazione completata con successo.")
            return os.path.abspath(dest)

        except yt_dlp.utils.DownloadError as e:
            if "404" in str(e): raise VideoNotFoundError(f"Video non trovato: {url}")
            raise NetworkError(f"Errore di rete: {e}")
        except SubtitleError:
            raise
        except Exception as e:
            raise SubtitleError(f"Errore imprevisto: {e}")

    def _create_logger(self):
        class MyLogger:
            def debug(self, msg): self.owner.log(msg)
            def warning(self, msg): self.owner.log(f"WARNING: {msg}")
            def error(self, msg): self.owner.log(f"ERROR: {msg}")
        logger = MyLogger()
        logger.owner = self
        return logger