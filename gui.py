import datetime
import os
import re
import subprocess
import threading
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk

from config import AppConfig
from ffmpeg_manager import FFmpegManager
from logic import (
    DependencyError,
    NetworkError,
    SubtitleError,
    SubtitleLogic,
    SubtitlesUnavailableError,
    VideoNotFoundError,
    get_program_dir,
    is_ytdlp_breakage,
)

# Impostazione aspetto
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

URL_PATTERN = re.compile(r'^https?://(www\.)?(youtube\.com|youtu\.be|m\.youtube\.com)')
LANG_CODE_RE = re.compile(r'^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$')


def is_valid_youtube_url(url: str) -> bool:
    """Verifica che l'URL sia un link YouTube valido (http/https)."""
    return bool(URL_PATTERN.match(url.strip()))

class SubtitleDownloaderGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("YouTube Subtitle Downloader Pro")
        self.geometry("700x800")

        self.ffmpeg_mgr = FFmpegManager()
        self.app_config = AppConfig()
        self.logic = SubtitleLogic(logger=self, ffmpeg_mgr=self.ffmpeg_mgr, app_config=self.app_config)
        
        # Configurazione griglia
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1) # L'area log si espande

        # --- Tabview Section ---
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="nsew")
        
        self.tab_download = self.tabview.add("Download")
        self.tab_settings = self.tabview.add("Impostazioni")

        # --- Download Tab Content ---
        self.tab_download.grid_columnconfigure(0, weight=1)

        # Sezione URL
        self.url_label = ctk.CTkLabel(self.tab_download, text="URL Video / Playlist YouTube (uno per riga):", font=("Segoe UI", 14, "bold"))
        self.url_label.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")

        self.url_frame = ctk.CTkFrame(self.tab_download, fg_color="transparent")
        self.url_frame.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.url_frame.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(self.url_frame, placeholder_text="https://www.youtube.com/watch?v=...")
        self.url_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        
        self.paste_btn = ctk.CTkButton(self.url_frame, text="Incolla", width=80, command=self.paste_url)
        self.paste_btn.grid(row=0, column=1)

        # Sezione Opzioni
        self.options_frame = ctk.CTkFrame(self.tab_download)
        self.options_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.options_frame.grid_columnconfigure((0, 1), weight=1)

        # Selezione Lingua
        self.lang_label = ctk.CTkLabel(self.options_frame, text="Lingua Sottotitoli:", font=("Segoe UI", 12))
        self.lang_label.grid(row=0, column=0, padx=15, pady=(10, 0), sticky="w")
        
        self.lang_combo = ctk.CTkComboBox(self.options_frame, values=["Inserisci URL e clicca 'Carica'..."])
        self.lang_combo.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="ew")
        self.lang_combo.set("Inserisci URL e clicca 'Carica'...")

        # Selezione Formato
        self.format_label = ctk.CTkLabel(self.options_frame, text="Formato File:", font=("Segoe UI", 12))
        self.format_label.grid(row=0, column=1, padx=15, pady=(10, 0), sticky="w")
        
        self.format_combo = ctk.CTkComboBox(self.options_frame, values=["srt", "vtt", "txt"])
        self.format_combo.grid(row=1, column=1, padx=15, pady=(0, 10), sticky="ew")
        self.format_combo.set("srt")

        # Filtro Sorgente
        self.filter_frame = ctk.CTkFrame(self.options_frame, fg_color="transparent")
        self.filter_frame.grid(row=2, column=0, columnspan=2, padx=15, pady=(0, 10), sticky="w")

        self.manual_var = ctk.BooleanVar(value=True)
        self.auto_var = ctk.BooleanVar(value=True)
        
        self.cb_manual = ctk.CTkCheckBox(self.filter_frame, text="Sottotitoli Manuali", variable=self.manual_var)
        self.cb_manual.pack(side="left", padx=(0, 20))
        
        self.cb_auto = ctk.CTkCheckBox(self.filter_frame, text="Sottotitoli Automatici", variable=self.auto_var)
        self.cb_auto.pack(side="left")

        # Fetch Languages Button
        self.fetch_btn = ctk.CTkButton(self.options_frame, text="Carica Lingue Disponibili", 
                                       fg_color="#2c3e50", hover_color="#34495e", 
                                       command=self.load_languages)
        self.fetch_btn.grid(row=3, column=0, columnspan=2, padx=15, pady=(0, 15), sticky="ew")

        # Sezione Destinazione
        self.dest_label = ctk.CTkLabel(self.tab_download, text="Cartella di destinazione:", font=("Segoe UI", 14, "bold"))
        self.dest_label.grid(row=3, column=0, padx=20, pady=(10, 5), sticky="w")

        self.dest_frame = ctk.CTkFrame(self.tab_download, fg_color="transparent")
        self.dest_frame.grid(row=4, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.dest_frame.grid_columnconfigure(0, weight=1)

        self.dest_entry = ctk.CTkEntry(self.dest_frame)
        self.dest_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.dest_entry.insert(0, ".")
        
        self.browse_btn = ctk.CTkButton(self.dest_frame, text="Sfoglia", width=80, command=self.browse_folder)
        self.browse_btn.grid(row=0, column=1)

        # Sezione Azioni
        self.action_frame = ctk.CTkFrame(self.tab_download, fg_color="transparent")
        self.action_frame.grid(row=5, column=0, padx=20, pady=10, sticky="ew")
        self.action_frame.grid_columnconfigure(0, weight=1)

        self.download_btn = ctk.CTkButton(self.action_frame, text="Scarica Sottotitoli", 
                                                 font=("Segoe UI", 14, "bold"), height=40, border_width=0, command=self.start_download_thread)
        self.download_btn.grid(row=0, column=0, padx=0, pady=5, sticky="ew")

        self.is_downloading = False # Stato download per soft-disable
        self.original_btn_color = self.download_btn.cget("fg_color")

        self.progress_bar = ctk.CTkProgressBar(self.action_frame)
        self.progress_bar.grid(row=1, column=0, padx=0, pady=5, sticky="ew")
        self.progress_bar.set(0)

        # --- Settings Tab Content ---
        self.tab_settings.grid_columnconfigure(0, weight=1)

        self.ffmpeg_label = ctk.CTkLabel(self.tab_settings, text="Configurazione FFmpeg:", font=("Segoe UI", 14, "bold"))
        self.ffmpeg_label.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")

        self.ffmpeg_frame = ctk.CTkFrame(self.tab_settings, fg_color="transparent")
        self.ffmpeg_frame.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.ffmpeg_frame.grid_columnconfigure(0, weight=1)

        # Visualizzazione versione
        self.ffmpeg_ver_label = ctk.CTkLabel(self.ffmpeg_frame, text="Versione: Caricamento...", font=("Segoe UI", 12, "italic"))
        self.ffmpeg_ver_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.ffmpeg_entry = ctk.CTkEntry(self.ffmpeg_frame)
        self.ffmpeg_entry.grid(row=1, column=0, padx=(0, 10), sticky="ew")
        initial_ffmpeg = self.ffmpeg_mgr.ffmpeg_path or "Non configurato / Automatico"
        self.ffmpeg_entry.insert(0, initial_ffmpeg)

        self.ffmpeg_browse_btn = ctk.CTkButton(self.ffmpeg_frame, text="Sfoglia", width=80, command=self.browse_ffmpeg)
        self.ffmpeg_browse_btn.grid(row=1, column=1, padx=(0, 10))

        self.ffmpeg_save_btn = ctk.CTkButton(self.ffmpeg_frame, text="Salva", width=80, fg_color="#27ae60", hover_color="#2ecc71", command=self.save_ffmpeg_path)
        self.ffmpeg_save_btn.grid(row=1, column=2)

        self.ffmpeg_update_btn = ctk.CTkButton(self.ffmpeg_frame, text="Aggiorna FFmpeg", width=150, fg_color="#e67e22", hover_color="#d35400", command=self.update_ffmpeg)
        self.ffmpeg_update_btn.grid(row=2, column=0, columnspan=3, padx=(0, 10), pady=(10, 0), sticky="e")

        # Sezione Retry
        self.retry_label = ctk.CTkLabel(self.tab_settings, text="Impostazioni Retry:", font=("Segoe UI", 14, "bold"))
        self.retry_label.grid(row=2, column=0, padx=20, pady=(20, 5), sticky="w")

        self.retry_frame = ctk.CTkFrame(self.tab_settings, fg_color="transparent")
        self.retry_frame.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.retry_frame.grid_columnconfigure((0, 1), weight=1)

        self.retry_attempts_entry = ctk.CTkEntry(self.retry_frame, placeholder_text="Tentativi (es. 2)")
        self.retry_attempts_entry.insert(0, str(self.app_config.retry_attempts))
        self.retry_attempts_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")

        self.retry_delay_entry = ctk.CTkEntry(self.retry_frame, placeholder_text="Delay tra i tentativi (s)")
        self.retry_delay_entry.insert(0, str(self.app_config.retry_delay))
        self.retry_delay_entry.grid(row=0, column=1, padx=(0, 10), sticky="ew")

        self.retry_save_btn = ctk.CTkButton(self.retry_frame, text="Salva", width=80, fg_color="#27ae60", hover_color="#2ecc71", command=self.save_retry_settings)
        self.retry_save_btn.grid(row=0, column=2)

        # Controllo versione iniziale
        self.refresh_ffmpeg_version()

        # Check yt-dlp version in background
        self.check_ytdlp_version()

        # --- Log Section (Main Window) ---
        self.log_label = ctk.CTkLabel(self, text="Log di sistema:", font=("Segoe UI", 12))
        self.log_label.grid(row=1, column=0, padx=20, pady=(10, 0), sticky="w")

        self.log_area = ctk.CTkTextbox(self, state='disabled', font=("Consolas", 12))
        self.log_area.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="nsew")

        # --- Bottom Actions (Main Window) ---
        self.bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.bottom_frame.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="ew")

        
        self.open_folder_btn = ctk.CTkButton(self.bottom_frame, text="Apri Cartella", 
                                            fg_color="#461ae7", hover_color="#0004FF",
                                            command=self.open_dest_folder, state="disabled")
        self.open_folder_btn.pack(side="right")

    # --- Logic Methods ---

    def log(self, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        def update():
            self.log_area.configure(state='normal')
            self.log_area.insert("end", f"[{timestamp}] {message}\n")
            self.log_area.see("end")
            self.log_area.configure(state='disabled')

        self.after(0, update)

    def ytdlp_update_hint(self):
        self.log("Suggerimento: aggiorna yt-dlp eseguendo 'pip install -U yt-dlp' o scarica l'ultima versione del programma.")

    def check_ytdlp_version(self):
        def task():
            result = self.logic.check_ytdlp_update()
            if result is None:
                self.log("Controllo versione yt-dlp non riuscito (rete non disponibile?).")
            elif result[0] == "aggiornato":
                self.log(f"yt-dlp aggiornato all'ultima versione ({result[1]}).")
            else:
                _, installed, latest = result
                self.log(f"Attenzione: yt-dlp {installed} obsoleto. Ultima versione disponibile: {latest}")
                self.ytdlp_update_hint()

        threading.Thread(target=task, daemon=True).start()

    def paste_url(self):
        try:
            clipboard_text = self.clipboard_get()
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, clipboard_text)
        except Exception:
            self.log("Errore: Clipboard vuota o non accessibile.")

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.dest_entry.delete(0, "end")
            self.dest_entry.insert(0, folder)

    def browse_ffmpeg(self):
        file_path = filedialog.askopenfilename(
            title="Seleziona ffmpeg.exe", 
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")]
        )
        if file_path:
            self.ffmpeg_entry.delete(0, "end")
            self.ffmpeg_entry.insert(0, file_path)

    def save_ffmpeg_path(self):
        path = self.ffmpeg_entry.get().strip()
        if not path:
            messagebox.showwarning("Attenzione", "Inserisci un percorso valido per FFmpeg.")
            return
        
        if self.ffmpeg_mgr.set_ffmpeg_path(path):
            self.log("Configurazione FFmpeg salvata correttamente.")
            messagebox.showinfo("Successo", "Percorso FFmpeg salvato con successo!")
            self.refresh_ffmpeg_version()
        else:
            messagebox.showerror("Errore", "Il percorso selezionato non è valido o il file non esiste.")

    def save_retry_settings(self):
        try:
            attempts_raw = self.retry_attempts_entry.get().strip()
            delay_raw = self.retry_delay_entry.get().strip()
            if not attempts_raw or not delay_raw:
                messagebox.showwarning("Attenzione", "Inserisci sia i tentativi sia il delay.")
                return
            attempts = int(attempts_raw)
            delay = float(delay_raw)
            self.app_config.retry_attempts = attempts
            self.app_config.retry_delay = delay
            self.log(f"Impostazioni retry salvate: {attempts} tentativi, {delay}s di delay.")
            messagebox.showinfo("Successo", "Impostazioni retry salvate con successo!")
        except ValueError as e:
            messagebox.showerror("Errore", str(e))

    def refresh_ffmpeg_version(self):
        def task():
            version = self.ffmpeg_mgr.get_local_version()
            # Aggiornamento UI sicuro dal thread
            self.after(0, lambda: self.ffmpeg_ver_label.configure(text=f"Versione: {version or 'Sconosciuta'}"))
        
        threading.Thread(target=task, daemon=True).start()

    def update_ffmpeg(self):
        def task():
            self.log("Controllo aggiornamenti FFmpeg in corso...")
            update_info = self.ffmpeg_mgr.check_for_update()
            # Tutte le chiamate UI devono avvenire sul main thread
            self.after(0, lambda: self._handle_ffmpeg_update_info(update_info))

        threading.Thread(target=task, daemon=True).start()

    def _handle_ffmpeg_update_info(self, update_info):
        """Mostra l'esito del controllo aggiornamenti FFmpeg (main thread)."""
        if update_info["update_available"]:
            if update_info["local"]:
                msg = f"Nuova versione disponibile: {update_info['remote']} (Installata: {update_info['local']})\nVuoi aggiornare?"
            else:
                msg = f"FFmpeg non installato. Ultima versione disponibile: {update_info['remote']}\nVuoi installarlo?"
            if messagebox.askyesno("Aggiornamento Disponibile", msg):
                self.log("Download e installazione di FFmpeg in corso...")
                threading.Thread(target=self._ffmpeg_download_task, daemon=True).start()
            else:
                self.log("Aggiornamento annullato dall'utente.")
        else:
            if update_info["local"]:
                self.log(f"FFmpeg è già aggiornato (Versione: {update_info['local']}).")
                messagebox.showinfo("Info", "FFmpeg è già alla versione più recente.")
            else:
                self.log("Impossibile verificare lo stato di FFmpeg (non installato o rete non disponibile).")

    def _ffmpeg_download_task(self):
        success = self.ffmpeg_mgr.download_and_install(get_program_dir())
        if success:
            self.log("FFmpeg aggiornato con successo!")
            self.after(0, lambda: (messagebox.showinfo("Successo", "FFmpeg è stato aggiornato all'ultima versione."),
                                   self.refresh_ffmpeg_version()))
        else:
            self.log("Errore durante l'aggiornamento di FFmpeg.")
            self.after(0, lambda: messagebox.showerror("Errore", "Impossibile aggiornare FFmpeg automaticamente."))

    def open_dest_folder(self):

        path = self.dest_entry.get().strip() or "."
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            subprocess.Popen(["explorer", abs_path])
        else:
            self.log("Errore: La cartella non esiste.")

    def _split_urls(self) -> list:
        """Estrae la lista di URL (uno per riga) dal campo di input, ignorando le righe vuote."""
        return [u.strip() for u in self.url_entry.get().splitlines() if u.strip()]

    def load_languages(self):
        urls = self._split_urls()
        if not urls:
            messagebox.showwarning("Attenzione", "Per favore, inserisci prima l'URL del video.")
            return
        for url in urls:
            if not is_valid_youtube_url(url):
                messagebox.showwarning("Attenzione", f"URL non valido: {url}\nDeve essere un link YouTube (http/https).")
                return

        self.fetch_btn.configure(state="disabled", text="Caricamento...")
        self.download_btn.configure(state="disabled")

        def task():
            try:
                merged = {}
                for url in urls:
                    subs = self.logic.get_available_subtitles(url)
                    for s in subs:
                        key = (s['lang'], s['type'])
                        if key not in merged:
                            merged[key] = s
                    self.log(f"Caricate {len(subs)} lingue da: {url}")
                if not merged:
                    self.after(0, lambda: (self.lang_combo.configure(values=["Nessuno disponibile"]),
                                            self.lang_combo.set("Nessuno disponibile")))
                    self.log("Nessun sottotitolo disponibile per questi video.")
                else:
                    # Crea la lista dei nomi visualizzati (es. Italiano (man.)) e la mappa
                    # label -> codice lingua; l'aggiornamento UI avviene sul main thread.
                    display_list = [f"{s['name']} ({'man.' if s['type']=='manual' else 'auto'})" for s in merged.values()]
                    lang_map = {label: s['lang'] for label, s in zip(display_list, merged.values())}
                    self.after(0, lambda: self._set_languages(display_list, lang_map))
                    self.log(f"Trovate {len(merged)} lingue disponibili.")
            except SubtitleError as e:
                self.log(f"Errore caricamento lingue: {e}")
                self.after(0, lambda e=e: self._show_messagebox_error("Errore", str(e)))
            except Exception as e:
                self.log(f"Errore imprevisto: {e}")
                self.after(0, lambda e=e: self._show_messagebox_error("Errore Critico", f"Si è verificato un errore imprevisto: {e}"))
            finally:
                self.after(0, lambda: (self.fetch_btn.configure(state="normal", text="Carica Lingue Disponibili"),
                                        # Non riabilitare il download se è già in corso
                                        self.download_btn.configure(state="normal" if not self.is_downloading else "disabled")))

        threading.Thread(target=task, daemon=True).start()

    def _set_languages(self, display_list: list, lang_map: dict):
        """Aggiorna la combo delle lingue dal main thread (chiamato via self.after)."""
        self.current_subs_map = lang_map
        self.lang_combo.configure(values=display_list)
        self.lang_combo.set(display_list[0])

    def _show_messagebox_error(self, title: str, msg: str):
        """Mostra un errore dal main thread, con suggerimento yt-dlp se rilevante."""
        if is_ytdlp_breakage(msg):
            self.ytdlp_update_hint()
        messagebox.showerror(title, msg)

    def _resolve_lang(self, selected_lang_text: str) -> Optional[str]:
        """Risolve il codice lingua: dalla mappa se la selezione è valida, altrimenti dall'input manuale."""
        if hasattr(self, 'current_subs_map') and selected_lang_text in self.current_subs_map:
            return self.current_subs_map[selected_lang_text]
        lang = selected_lang_text.strip()
        if not LANG_CODE_RE.fullmatch(lang):
            return None
        self.log(f"Lingua inserita manualmente: {lang} (non presente nella lista caricata).")
        return lang

    def progress_hook(self, d):
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0%').replace('%', '')
            try:
                value = float(p) / 100.0
            except ValueError:
                return
            self.after(0, lambda v=value: self.progress_bar.set(v))
        elif d['status'] == 'finished':
            self.after(0, lambda: self.progress_bar.set(1.0))

    def start_download_thread(self):
        urls = self._split_urls()
        dest = self.dest_entry.get().strip() or "."
        fmt = self.format_combo.get()

        if not urls:
            messagebox.showwarning("Attenzione", "Per favore, inserisci prima l'URL del video.")
            return
        for url in urls:
            if not is_valid_youtube_url(url):
                messagebox.showwarning("Attenzione", f"URL non valido: {url}\nDeve essere un link YouTube (http/https).")
                return
        
        # Risolve il codice della lingua selezionata
        lang = self._resolve_lang(self.lang_combo.get())
        if not lang:
            messagebox.showwarning("Attenzione", "Seleziona una lingua oppure inserisci un codice valido (es. 'it' o 'pt-BR').")
            return

        # Filtri
        manual_only = not self.auto_var.get()
        auto_only = not self.manual_var.get()
        
        if manual_only and auto_only:
             messagebox.showwarning("Attenzione", "Seleziona almeno un tipo di sottotitolo (Manuale o Automatico).")
             return

        if self.is_downloading:
            return

        self.is_downloading = True
        self.download_btn.configure(text="Download in corso...", fg_color="#5c5c5c")
        self.open_folder_btn.configure(state="disabled")
        self.progress_bar.set(0)

        def task():
            try:
                if len(urls) == 1:
                    result_path = self.logic.download_subtitles(
                        urls[0],
                        lang=lang,
                        dest=dest,
                        format=fmt,
                        auto_only=auto_only,
                        manual_only=manual_only,
                        progress_hook=self.progress_hook,
                    )
                    self.after(0, lambda: self._on_download_success_single(result_path))
                else:
                    result = self.logic.download_queue(
                        urls,
                        lang=lang,
                        dest=dest,
                        format=fmt,
                        auto_only=auto_only,
                        manual_only=manual_only,
                        progress_hook=self.progress_hook,
                    )
                    self.after(0, lambda: self._on_download_success_queue(result))
            except VideoNotFoundError as e:
                self.after(0, lambda e=e: self._on_download_error("Video non trovato", str(e), "ERRORE:"))
            except SubtitlesUnavailableError as e:
                self.after(0, lambda e=e: self._on_download_error("Sottotitoli non disponibili", str(e), "ERRORE:"))
            except NetworkError as e:
                self.after(0, lambda e=e: self._on_download_error("Errore di Rete", str(e), "ERRORE DI RETE:"))
            except DependencyError as e:
                self.after(0, lambda e=e: self._on_download_error("Errore Dipendenze", str(e), "ERRORE DIPENDENZE:"))
            except SubtitleError as e:
                self.after(0, lambda e=e: self._on_download_error("Errore", str(e), "ERRORE:"))
            except Exception as e:
                self.after(0, lambda e=e: self._on_download_error(
                    "Errore Critico", f"Si è verificato un errore imprevisto:\n{e}", "ERRORE CRITICO:"))

        threading.Thread(target=task, daemon=True).start()

    # --- Callback di esito (eseguiti sul main thread via self.after) ---

    def _reset_download_ui(self):
        self.is_downloading = False
        self.download_btn.configure(text="Scarica Sottotitoli", fg_color=self.original_btn_color)
        self.focus()

    def _on_download_success_single(self, result_path: str):
        self.log(f"Completato! File salvati in: {result_path}")
        self.open_folder_btn.configure(state="normal")
        self._reset_download_ui()
        messagebox.showinfo("Successo", "Sottotitoli scaricati con successo!")

    def _on_download_success_queue(self, result: dict):
        summary = f"Coda completata: {result['successi']} riusciti, {result['errori']} falliti."
        self.log(summary)
        self.open_folder_btn.configure(state="normal")
        self._reset_download_ui()
        if result['errori']:
            messagebox.showwarning("Coda completata con errori", summary + "\nConsulta il log per i dettagli.")
        else:
            messagebox.showinfo("Successo", summary)

    def _on_download_error(self, title: str, msg: str, log_prefix: str = "ERRORE:"):
        self.log(f"{log_prefix} {msg}")
        if is_ytdlp_breakage(msg):
            self.ytdlp_update_hint()
        self._reset_download_ui()
        messagebox.showerror(title, msg)

if __name__ == "__main__":
    app = SubtitleDownloaderGUI()
    app.mainloop()