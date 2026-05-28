import yt_dlp
import os
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import threading
import subprocess
import shutil
import sys

def get_program_dir():
    """ Get the directory where the executable or script is located """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(".")

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temporary folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = get_program_dir()
    return os.path.join(base_path, relative_path)

class SubtitleDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Subtitle Downloader")
        self.root.geometry("600x500")

        # Main Container
        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # URL Field
        ttk.Label(main_frame, text="URL Video YouTube / Short:").pack(anchor=tk.W)
        url_frame = ttk.Frame(main_frame)
        url_frame.pack(fill=tk.X, pady=(0, 10))
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(url_frame, text="Incolla", command=self.paste_url).pack(side=tk.RIGHT, padx=(5, 0))

        # Language Field
        ttk.Label(main_frame, text="Codice Lingua (es. 'it', 'en', 'uk') [default: it]:").pack(anchor=tk.W)
        self.lang_entry = ttk.Entry(main_frame, width=70)
        self.lang_entry.insert(0, "it")
        self.lang_entry.pack(fill=tk.X, pady=(0, 10))

        # Destination Field
        dest_frame = ttk.Frame(main_frame)
        dest_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(dest_frame, text="Cartella di destinazione:").pack(side=tk.LEFT)
        self.dest_entry = ttk.Entry(dest_frame)
        self.dest_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        self.dest_entry.insert(0, ".")
        ttk.Button(dest_frame, text="Sfoglia", command=self.browse_folder).pack(side=tk.RIGHT)

        # Download Button
        self.download_btn = ttk.Button(main_frame, text="Scarica Sottotitoli", command=self.start_download_thread)
        self.download_btn.pack(pady=10)

        # Log Window
        ttk.Label(main_frame, text="Log del programma:").pack(anchor=tk.W)
        self.log_area = scrolledtext.ScrolledText(main_frame, height=15, state='disabled')
        self.log_area.pack(fill=tk.BOTH, expand=True, pady=(0, 0))

    def paste_url(self):
        try:
            clipboard_text = self.root.clipboard_get()
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, clipboard_text)
        except tk.TclError:
            self.log("Errore: Clipboard vuota o non accessibile.")

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.dest_entry.delete(0, tk.END)
            self.dest_entry.insert(0, folder)

    def log(self, message):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.configure(state='disabled')

    def start_download_thread(self):
        # Get inputs
        url = self.url_entry.get().strip()
        lang = self.lang_entry.get().strip() or 'it'
        dest = self.dest_entry.get().strip() or '.'

        if not url:
            self.log("Errore: L'URL non può essere vuoto.")
            return

        # Disable button to prevent multiple clicks
        self.download_btn.config(state=tk.DISABLED)
        
        # Run download in a separate thread so GUI doesn't freeze
        thread = threading.Thread(target=self.run_download, args=(url, lang, dest), daemon=True)
        thread.start()

    def download_ffmpeg(self):
        """Downloads and extracts FFmpeg binaries to the program directory."""
        import urllib.request
        import zipfile

        # Passiamo al build 'full' invece di 'essentials' per garantire tutte le dipendenze/DLL
        url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip"
        prog_dir = get_program_dir()
        zip_path = os.path.join(prog_dir, "ffmpeg.zip")
        
        try:
            self.log("Download di FFmpeg in corso (circa 100MB)...")
            urllib.request.urlretrieve(url, zip_path)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Find the directory containing the binaries inside the zip
                bin_folder = None
                for member in zip_ref.namelist():
                    if member.endswith('bin/') or ( '/bin/' in member and member.split('/')[1] == 'bin'):
                        # We want the path to the bin folder, e.g., "ffmpeg-7.1-essentials_build/bin/"
                        bin_folder = '/'.join(member.split('/')[:-1]) + '/' 
                        break
                
                if not bin_folder:
                    # Fallback: search for ffmpeg.exe and get its folder
                    for member in zip_ref.namelist():
                        if member.endswith('ffmpeg.exe'):
                            bin_folder = os.path.dirname(member) + '/'
                            break

                if bin_folder:
                    self.log(f"Estrazione di FFmpeg da {bin_folder}...")
                    for member in zip_ref.namelist():
                        if member.startswith(bin_folder):
                            filename = os.path.basename(member)
                            if filename: # Avoid extracting the folder itself
                                source = zip_ref.open(member)
                                target = open(os.path.join(prog_dir, filename), 'wb')
                                shutil.copyfileobj(source, target)
                                target.close()
                                source.close()
                else:
                    raise Exception("Impossibile trovare la cartella bin nell'archivio FFmpeg.")
            
            os.remove(zip_path)
            self.log("FFmpeg installato correttamente nella cartella del programma.")
            return True
        except Exception as e:
            if os.path.exists(zip_path):
                os.remove(zip_path)
            self.log(f"Errore durante il download di FFmpeg: {e}")
            return False

    def ensure_dependencies(self):
        """Checks for ffmpeg and nodejs (JS runtime). Downloads ffmpeg locally if missing."""
        # 1. Check FFmpeg in program directory using absolute path
        ffmpeg_path = os.path.join(get_program_dir(), "ffmpeg.exe")
        ffmpeg_exists = os.path.exists(ffmpeg_path)
        
        if not ffmpeg_exists:
            self.log("FFmpeg non trovato nella cartella del programma.")
            if self.download_ffmpeg():
                ffmpeg_exists = os.path.exists(ffmpeg_path)
            else:
                self.log("Errore critico: Impossibile scaricare FFmpeg.")

        # 2. Check Node.js and find its path explicitly for yt-dlp
        node_path = None
        try:
            result = subprocess.run(["where", "node"], capture_output=True, encoding='utf-8', errors='replace', check=True)
            node_path = result.stdout.strip().split('\n')[0]
            self.log(f"JS Runtime trovato: {node_path}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.log("JS Runtime (Node.js) non trovato. Tentativo di installazione...")
            try:
                subprocess.run(["choco", "install", "nodejs", "-y"], check=True, capture_output=True)
                # Search for node path after installation
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

    def convert_vtt_to_srt(self, vtt_path):
        """Manually converts a .vtt file to .srt using the local ffmpeg.exe."""
        srt_path = os.path.splitext(vtt_path)[0] + ".srt"
        try:
            # Use absolute path to ensure it works regardless of CWD
            ffmpeg_exe = os.path.join(get_program_dir(), "ffmpeg.exe")
            if not os.path.exists(ffmpeg_exe):
                self.log(f"Errore: {ffmpeg_exe} non trovato per la conversione.")
                return False

            cmd = [
                ffmpeg_exe, "-y", 
                "-i", vtt_path, 
                srt_path
            ]
            # Capture stderr to log the exact reason for failure (e.g., missing DLLs)
            result = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace')
            if result.returncode != 0:
                self.log(f"Errore FFmpeg durante la conversione di {os.path.basename(vtt_path)}:\n{result.stderr}")
                return False
            
            # Remove the original .vtt file after successful conversion
            if os.path.exists(vtt_path):
                os.remove(vtt_path)
            return True
        except Exception as e:
            self.log(f"Errore critico durante la conversione di {os.path.basename(vtt_path)}: {e}")
            return False

    def run_download(self, url, lang, dest):
        try:
            # Ensure FFmpeg and JS Runtime are available first
            ffmpeg_ok, node_path = self.ensure_dependencies()
            if not ffmpeg_ok:
                self.log("\nERRORE: FFmpeg è necessario per convertire i sottotitoli in .srt")
                self.log("Il processo verrà interrotto.")
                self.root.after(0, lambda: self.download_btn.config(state=tk.NORMAL))
                return

            # If we found a node path, add it to the current process environment PATH 
            # so yt-dlp can find the JS runtime without needing a system restart.
            if node_path:
                node_dir = os.path.dirname(node_path)
                if node_dir not in os.environ['PATH']:
                    os.environ['PATH'] = node_dir + os.pathsep + os.environ['PATH']
                    self.log(f"JS Runtime attivato tramite percorso: {node_dir}")

            # Use a custom logger for yt-dlp to capture output into our log area
            class MyLogger:
                def debug(self, msg): SubtitleDownloaderGUI.static_log(msg)
                def warning(self, msg): SubtitleDownloaderGUI.static_log(f"WARNING: {msg}")
                def error(self, msg): SubtitleDownloaderGUI.static_log(f"ERROR: {msg}")

            # Set the static logger reference
            SubtitleDownloaderGUI.current_instance = self
            
            if not os.path.exists(dest):
                os.makedirs(dest)
                self.log(f"Creazione cartella: {dest}")

            # FIX: Usiamo get_program_dir() invece di get_resource_path().
            # FFmpeg viene scaricato nella cartella dell'app, non nella cartella temporanea di PyInstaller.
            ffmpeg_abs_path = get_program_dir()

            ydl_opts = {
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': [lang],
                'skip_download': True,
                'outtmpl': os.path.join(dest, '%(title)s.%(ext)s'),
                'ffmpeg_location': ffmpeg_abs_path, 
                'postprocessors': [{
                    'key': 'FFmpegSubtitlesConvertor',
                    'format': 'srt',
                }],
                'logger': MyLogger(),
            }
            if node_path:
                ydl_opts['js_runtimes'] = {'Node': {'executable': node_path}}

            self.log(f"Avvio ricerca sottotitoli ({lang}) per: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                filename = ydl.prepare_filename(info)
                ydl.download([url])

                # --- MANUAL FALLBACK CONVERSION ---
                # Check for any .vtt files created in the destination folder that match this video
                video_title_slug = os.path.splitext(os.path.basename(filename))[0]
                converted_any = False
                for f in os.listdir(dest):
                    if f.endswith(".vtt") and video_title_slug in f:
                        vtt_full_path = os.path.join(dest, f)
                        self.log(f"Conversione manuale di {f} -> .srt...")
                        if self.convert_vtt_to_srt(vtt_full_path):
                            converted_any = True

                # Final check for .srt files
                found_srt = False
                for f in os.listdir(dest):
                    if f.endswith(".srt") and video_title_slug in f:
                        found_srt = True
                        break
                
                if found_srt:
                    self.log("\n--- Download e conversione in .srt completati con successo! ---")
                else:
                    self.log("\nATTENZIONE: Non sono stati trovati file .srt.")
                    self.log("Possibili cause: sottotitoli non disponibili per questa lingua o errore FFmpeg.")

            self.log(f"File salvati in: {os.path.abspath(dest)}")

        except Exception as e:
            err_msg = str(e)
            if "JSON" in err_msg or "extract_info" in err_msg:
                self.log("\nERRORE DI ESTRAZIONE DATI: Il formato dei dati di YouTube è cambiato.")
                self.log("Per risolvere, aggiorna yt-dlp eseguendo: pip install -U yt-dlp")
                self.log("Oppure, se usi l'eseguibile, scarica l'ultima versione del programma.")
            else:
                self.log(f"\nErrore critico: {err_msg}")
        finally:
            # Re-enable button in the main thread
            self.root.after(0, lambda: self.download_btn.config(state=tk.NORMAL))

    @staticmethod
    def static_log(msg):
        if hasattr(SubtitleDownloaderGUI, 'current_instance'):
            SubtitleDownloaderGUI.current_instance.log(msg)

if __name__ == "__main__":
    root = tk.Tk()
    app = SubtitleDownloaderGUI(root)
    root.mainloop()