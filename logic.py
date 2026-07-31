import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

import yt_dlp

from ffmpeg_manager import FFmpegManager


# --- Eccezioni personalizzate ---
class SubtitleError(Exception):
    """Eccezione base per il downloader di sottotitoli."""
    pass


class VideoNotFoundError(SubtitleError):
    """Sollevata quando il video non può essere trovato."""
    pass


class SubtitlesUnavailableError(SubtitleError):
    """Sollevata quando i sottotitoli non sono disponibili nella lingua richiesta."""
    pass


class NetworkError(SubtitleError):
    """Sollevata in caso di errori legati alla rete."""
    pass


class DependencyError(SubtitleError):
    """Sollevata quando ffmpeg o nodejs mancano e non possono essere installati."""
    pass


# --- Utility ---
def get_program_dir() -> str:
    """Restituisce la directory in cui si trova lo script o l'eseguibile corrente."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


YTDLP_UPDATE_MARKERS = ("JSON", "extract_info", "Unable to extract", "Unsupported", "has no attribute")


def is_ytdlp_breakage(message: str) -> bool:
    """Rileva se un messaggio d'errore è probabilmente dovuto a yt-dlp obsoleto."""
    return any(marker in message for marker in YTDLP_UPDATE_MARKERS)


# --- Logica principale ---
class SubtitleLogic:
    def __init__(self, logger=None):
        self.logger = logger
        self.ffmpeg_mgr = FFmpegManager()

    def log(self, msg: str) -> None:
        if self.logger and hasattr(self.logger, 'log'):
            self.logger.log(msg)
        else:
            print(msg)

    def check_ytdlp_update(self) -> Optional[tuple]:
        """
        Confronta la versione di yt-dlp installata con l'ultima disponibile su PyPI.

        Returns:
            ("aggiornato", installed) se tutto ok, ("obsoleto", installed, latest)
            se è disponibile un aggiornamento, None se il controllo fallisce (es. offline).
        """
        try:
            installed = yt_dlp.version.__version__
            with urllib.request.urlopen("https://pypi.org/pypi/yt-dlp/json", timeout=15) as response:
                data = json.loads(response.read().decode())
            latest = data.get("info", {}).get("version", installed)
            if latest != installed:
                return ("obsoleto", installed, latest)
            return ("aggiornato", installed)
        except Exception:
            return None

    def ensure_dependencies(self) -> tuple:
        """Verifica la presenza di FFmpeg e Node.js, tentando di installarli se mancanti."""
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

    def _with_retry(self, func: Callable, attempts: int = 2, delay: float = 2.0):
        """Esegue func con retry in caso di NetworkError, con backoff fisso."""
        last_error = None
        for attempt in range(attempts):
            try:
                return func()
            except NetworkError as e:
                last_error = e
                if attempt < attempts - 1:
                    self.log(f"Errore di rete, nuovo tentativo ({attempt + 1}/{attempts})...")
                    time.sleep(delay)
        raise last_error

    def get_available_subtitles(self, url: str) -> list:
        """Recupera la lista dei sottotitoli disponibili (manuali e automatici) per un video."""
        return self._with_retry(lambda: self._fetch_available_subtitles(url))

    def _fetch_available_subtitles(self, url: str) -> list:
        try:
            ydl_opts = {'skip_download': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                subs = info.get('subtitles', {})
                auto_subs = info.get('automatic_captions', {})

                available = []
                for lang, data in subs.items():
                    available.append({'lang': lang, 'name': data[0].get('name', lang), 'type': 'manual'})
                for lang, data in auto_subs.items():
                    available.append({'lang': lang, 'name': data[0].get('name', lang), 'type': 'auto'})
                return available
        except yt_dlp.utils.DownloadError as e:
            raise self._map_ytdlp_error(e, url)
        except Exception as e:
            raise SubtitleError(f"Errore imprevisto nell'estrazione delle lingue: {e}")

    def _map_ytdlp_error(self, error, url: str) -> SubtitleError:
        """Converte un DownloadError di yt-dlp in un errore della gerarchia del progetto."""
        message = str(error)
        exc = getattr(error, 'exc_info', None)
        if exc and isinstance(exc[1], urllib.error.HTTPError) and exc[1].code == 404:
            return VideoNotFoundError(f"Video non trovato o non accessibile: {url}")
        if "404" in message or "Unable to extract" in message:
            return VideoNotFoundError(f"Video non trovato o non accessibile: {url}")
        return NetworkError(f"Errore di rete durante l'estrazione dei dati: {error}")

    def convert_vtt_to_srt(self, vtt_path: str) -> bool:
        """Converte un file .vtt in .srt tramite FFmpeg, rimuovendo il file sorgente."""
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

    def _build_ydl_opts(self, url: str, lang: str, dest: str, format: str,
                        auto_only: bool, manual_only: bool,
                        progress_hook: Optional[Callable]) -> dict:
        """Costruisce le opzioni per yt-dlp in base alla lingua, al formato e ai filtri scelti."""
        if self.ffmpeg_mgr.ffmpeg_path:
            ffmpeg_abs_path = os.path.dirname(self.ffmpeg_mgr.ffmpeg_path)
        else:
            ffmpeg_abs_path = os.path.dirname(self.ffmpeg_mgr._get_default_path())

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

        if format == 'srt':
            ydl_opts['postprocessors'] = [{'key': 'FFmpegSubtitlesConvertor', 'format': 'srt'}]
        elif format == 'txt':
            ydl_opts['postprocessors'] = [{'key': 'FFmpegSubtitlesConvertor', 'format': 'srt'}]

        return ydl_opts

    def _find_matching_file(self, dest: str, slug: str, ext: str) -> Optional[str]:
        """Cerca nella cartella di destinazione un file che corrisponda allo slug del titolo."""
        if not os.path.isdir(dest):
            return None
        for f in os.listdir(dest):
            if f.endswith(ext) and slug in f:
                return os.path.join(dest, f)
        return None

    def download_subtitles(self, url: str, lang: str, dest: str, format: str = 'srt',
                           auto_only: bool = False, manual_only: bool = False,
                           progress_hook: Optional[Callable] = None) -> str:
        """
        Scarica i sottotitoli di un video YouTube nella lingua e nel formato richiesti.

        Args:
            url: L'URL del video.
            lang: Il codice lingua dei sottotitoli.
            dest: La cartella di destinazione dei file.
            format: Formato dei sottotitoli ('srt', 'vtt' o 'txt'). Default 'srt'.
            auto_only: Se True, tenta di scaricare solo le didascalie automatiche.
            manual_only: Se True, tenta di scaricare solo i sottotitoli manuali.
            progress_hook: Callback opzionale per il monitoraggio dell'avanzamento.

        Returns:
            str: Il percorso assoluto della cartella di destinazione in caso di successo.
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

            ydl_opts = self._build_ydl_opts(url, lang, dest, format, auto_only, manual_only, progress_hook)

            if node_path:
                ydl_opts['js_runtimes'] = {'Node': {'executable': node_path}}

            self.log(f"Avvio download sottotitoli ({lang}) per: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)

                video_title_slug = os.path.splitext(os.path.basename(filename))[0]

                if format == 'srt':
                    vtt_file = self._find_matching_file(dest, video_title_slug, ".vtt")
                    if vtt_file:
                        self.log(f"Conversione manuale di {os.path.basename(vtt_file)} -> .srt...")
                        self.convert_vtt_to_srt(vtt_file)

                ext = ".srt" if format in ('srt', 'txt') else ".vtt"
                found = self._find_matching_file(dest, video_title_slug, ext) is not None

                if not found:
                    raise SubtitlesUnavailableError(f"Sottotitoli non trovati per la lingua {lang}")

            self.log("Operazione completata con successo.")
            return os.path.abspath(dest)

        except yt_dlp.utils.DownloadError as e:
            raise self._map_ytdlp_error(e, url)
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
