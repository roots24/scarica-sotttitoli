import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
from typing import Callable, Optional

import requests
import yt_dlp

from config import AppConfig
from ffmpeg_manager import FFmpegManager, version_tuple


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


YTDLP_UPDATE_MARKERS = ("JSON", "extract_info", "Unable to extract", "Unsupported URL", "has no attribute")


def is_ytdlp_breakage(message: str) -> bool:
    """Rileva se un messaggio d'errore è probabilmente dovuto a yt-dlp obsoleto."""
    return any(marker in message for marker in YTDLP_UPDATE_MARKERS)


# --- Logica principale ---
class SubtitleLogic:
    def __init__(self, logger=None, ffmpeg_mgr: Optional[FFmpegManager] = None,
                 app_config: Optional[AppConfig] = None):
        self.logger = logger
        self.ffmpeg_mgr = ffmpeg_mgr or FFmpegManager()
        self.app_config = app_config or AppConfig()

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
            response = requests.get("https://pypi.org/pypi/yt-dlp/json", timeout=15)
            response.raise_for_status()
            data = response.json()
            latest = data.get("info", {}).get("version", installed)
            # Confronto numerico: le versioni nightly/dev (es. "2026.07.04.232701.dev.0")
            # non devono essere segnalate come obsolete rispetto all'ultima stabile.
            if version_tuple(installed) >= version_tuple(latest):
                return ("aggiornato", installed)
            return ("obsoleto", installed, latest)
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

        node_path = shutil.which("node")
        if node_path:
            self.log(f"JS Runtime trovato: {node_path}")
        else:
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

    def _with_retry(self, func: Callable, attempts: Optional[int] = None, delay: Optional[float] = None):
        """Esegue func con retry in caso di NetworkError, con backoff fisso configurabile.

        Se attempts/delay non sono specificati, usa i valori di AppConfig (persistiti in config.json).
        """
        attempts = attempts if attempts is not None else self.app_config.retry_attempts
        delay = delay if delay is not None else self.app_config.retry_delay
        total = max(1, attempts)
        last_error = None
        for attempt in range(total):
            try:
                return func()
            except NetworkError as e:
                last_error = e
                if attempt < total - 1:
                    self.log(f"Errore di rete, nuovo tentativo ({attempt + 1}/{total})...")
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

    def convert_srt_to_txt(self, srt_path: str) -> bool:
        """Converte un file .srt in .txt (solo testo, senza indici né timestamp), rimuovendo il file sorgente."""
        txt_path = os.path.splitext(srt_path)[0] + ".txt"
        try:
            with open(srt_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()

            out_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.upper().startswith("WEBVTT"):
                    continue
                if re.fullmatch(r'\d+', stripped):
                    continue
                if re.match(r'^\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}', stripped):
                    continue
                out_lines.append(stripped)

            if not out_lines:
                self.log(f"Nessun testo estraibile da {os.path.basename(srt_path)}")
                return False

            with open(txt_path, 'w', encoding='utf-8', newline='') as f:
                f.write("\n".join(out_lines) + "\n")
            os.remove(srt_path)
            return True
        except Exception as e:
            self.log(f"Errore critico durante la conversione srt->txt: {e}")
            return False

    def _build_ydl_opts(self, url: str, lang: str, dest: str, format: str,
                        auto_only: bool, manual_only: bool,
                        progress_hook: Optional[Callable],
                        outtmpl_suffix: str = "") -> dict:
        """Costruisce le opzioni per yt-dlp in base alla lingua, al formato e ai filtri scelti.

        outtmpl_suffix (es. ".auto") viene inserito nel nome dei file per evitare
        collisioni tra passate diverse (manuali vs automatici).
        """
        if self.ffmpeg_mgr.ffmpeg_path:
            ffmpeg_abs_path = os.path.dirname(self.ffmpeg_mgr.ffmpeg_path)
        else:
            ffmpeg_abs_path = os.path.dirname(self.ffmpeg_mgr._get_default_path())

        ydl_opts = {
            'writesubtitles': not auto_only,
            'writeautomaticsub': not manual_only,
            'subtitleslangs': [lang],
            'skip_download': True,
            'outtmpl': os.path.join(dest, f'%(title)s{outtmpl_suffix}.%(ext)s'),
            'ffmpeg_location': ffmpeg_abs_path,
            'logger': self._create_logger(),
            'progress_hooks': [progress_hook] if progress_hook else [],
        }

        if format == 'srt':
            ydl_opts['postprocessors'] = [{'key': 'FFmpegSubtitlesConvertor', 'format': 'srt'}]
        elif format == 'txt':
            ydl_opts['postprocessors'] = [{'key': 'FFmpegSubtitlesConvertor', 'format': 'srt'}]

        return ydl_opts

    def _snapshot_dir(self, dest: str) -> dict:
        """Snapshot dei file (nome -> (mtime_ns, size)) presenti prima dell'esecuzione."""
        snap = {}
        if not os.path.isdir(dest):
            return snap
        for name in os.listdir(dest):
            try:
                st = os.stat(os.path.join(dest, name))
                snap[name] = (st.st_mtime_ns, st.st_size)
            except OSError:
                continue
        return snap

    def _file_changed(self, dest: str, name: str, snapshot: dict) -> bool:
        """True se il file non esisteva prima o è stato riscritto durante questa esecuzione."""
        try:
            st = os.stat(os.path.join(dest, name))
        except OSError:
            return True
        return snapshot.get(name) != (st.st_mtime_ns, st.st_size)

    def _find_matching_file(self, dest: str, slug: str, ext: str, lang: Optional[str] = None,
                            snapshot: Optional[dict] = None) -> Optional[str]:
        """Cerca nella cartella di destinazione il file di sottotitoli corrispondente allo slug del titolo.

        Con lang specificato il match è esatto sul nome atteso (es. '<slug>.<lang>.srt'):
        evita falsi positivi con file stantii, file di altre lingue o titoli simili.
        snapshot esclude i file già presenti prima del download (snapshot pre-run) e NON
        riscritti in questa esecuzione: un file stantio sovrascritto ora conta come nuovo.
        """
        if not os.path.isdir(dest):
            return None
        snapshot = snapshot or {}
        expected = f"{slug}.{lang}{ext}" if lang else None
        for f in os.listdir(dest):
            if not self._file_changed(dest, f, snapshot):
                continue
            if expected:
                if f == expected:
                    return os.path.join(dest, f)
            elif f.endswith(ext) and slug in f:
                return os.path.join(dest, f)
        return None

    def _iter_entries(self, info: Optional[dict]) -> list:
        """Estrae le voci da processare: la singola info video o gli entries di una playlist."""
        if not info:
            return []
        if info.get('_type') == 'playlist' and info.get('entries'):
            return [e for e in info['entries'] if e]
        return [info]

    def download_queue(self, urls: list, lang: str, dest: str, format: str = 'srt',
                       auto_only: bool = False, manual_only: bool = False,
                       progress_hook: Optional[Callable] = None) -> dict:
        """Scarica i sottotitoli per una lista di URL (video o playlist) in sequenza.

        Continua dopo un errore su un singolo URL, loggando il problema.

        Returns:
            dict: Conteggio finale, es. {"successi": n, "errori": m}.
        """
        successi = 0
        errori = 0
        for url in urls:
            try:
                self.download_subtitles(
                    url, lang=lang, dest=dest, format=format,
                    auto_only=auto_only, manual_only=manual_only,
                    progress_hook=progress_hook,
                )
                successi += 1
            except SubtitleError as e:
                errori += 1
                self.log(f"Errore per {url}: {e}")
        return {"successi": successi, "errori": errori}

    def download_subtitles(self, url: str, lang: str, dest: str, format: str = 'srt',
                           auto_only: bool = False, manual_only: bool = False,
                           progress_hook: Optional[Callable] = None) -> str:
        """
        Scarica i sottotitoli di un video o di una playlist YouTube nella lingua e nel formato richiesti.

        Args:
            url: L'URL del video o della playlist.
            lang: Il codice lingua dei sottotitoli.
            dest: La cartella di destinazione dei file.
            format: Formato dei sottotitoli ('srt', 'vtt' o 'txt'). Default 'srt'.
            auto_only: Se True, tenta di scaricare solo le didascalie automatiche.
            manual_only: Se True, tenta di scaricare solo i sottotitoli manuali.
            progress_hook: Callback opzionale per il monitoraggio dell'avanzamento.

        Note:
            - Con entrambi i filtri attivi vengono eseguite due passate di yt-dlp: la passata
              automatica usa il suffisso '.auto' nel nome (es. 'Titolo.auto.en.vtt') per non
              sovrascrivere i sottotitoli manuali della stessa lingua.
            - Il formato 'txt' produce un vero file .txt: yt-dlp non supporta il txt, quindi
              il file viene prima convertito in .srt e poi ripulito da indici e timestamp.

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

            want_manual = not auto_only
            want_auto = not manual_only
            if not (want_manual or want_auto):
                raise SubtitlesUnavailableError("Nessun tipo di sottotitolo selezionato.")

            # Con entrambi i tipi selezionati servono due passate: yt-dlp con entrambi i flag
            # scarica solo i manuali per le lingue che li hanno. La passata automatica usa il
            # suffisso '.auto' nel nome per evitare collisioni con i file manuali.
            passes = []
            if want_manual:
                passes.append({"manual": True, "auto": False, "suffix": "", "label": "manuali"})
            if want_auto:
                passes.append({"manual": False, "auto": True,
                               "suffix": ".auto" if want_manual else "", "label": "automatici"})

            # Snapshot dei file già presenti: contano solo i file creati O riscritti
            # da QUESTA esecuzione, così un file stantio nella cartella di destinazione
            # non genera falsi successi (e un file riscaricato non viene perso).
            preexisting = self._snapshot_dir(dest)
            total_trovati = 0
            is_playlist = False

            for run in passes:
                ydl_opts = self._build_ydl_opts(url, lang, dest, format,
                                                not run["manual"], not run["auto"],
                                                progress_hook, run["suffix"])
                if node_path:
                    ydl_opts['js_runtimes'] = {'node': {'path': node_path}}

                self.log(f"Avvio download sottotitoli {run['label']} ({lang}) per: {url}")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    entries = self._iter_entries(info)

                    if not entries:
                        raise SubtitlesUnavailableError(f"Nessun video processato per: {url}")

                    is_playlist = is_playlist or info.get('_type') == 'playlist'

                    for entry in entries:
                        filename = ydl.prepare_filename(entry)
                        video_title_slug = os.path.splitext(os.path.basename(filename))[0]

                        if format == 'srt':
                            vtt_file = self._find_matching_file(dest, video_title_slug, ".vtt",
                                                                lang=lang, snapshot=preexisting)
                            if vtt_file:
                                self.log(f"Conversione manuale di {os.path.basename(vtt_file)} -> .srt...")
                                self.convert_vtt_to_srt(vtt_file)

                        if format == 'txt':
                            srt_file = self._find_matching_file(dest, video_title_slug, ".srt",
                                                                lang=lang, snapshot=preexisting)
                            if srt_file:
                                self.log(f"Conversione di {os.path.basename(srt_file)} -> .txt...")
                                self.convert_srt_to_txt(srt_file)

                        ext = ".txt" if format == 'txt' else (".srt" if format == 'srt' else ".vtt")
                        if self._find_matching_file(dest, video_title_slug, ext,
                                                    lang=lang, snapshot=preexisting):
                            total_trovati += 1
                        elif is_playlist:
                            self.log(f"Sottotitoli non trovati per: {entry.get('title') or entry.get('id') or url}")

            if total_trovati == 0:
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
