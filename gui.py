import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import os
import subprocess
from logic import SubtitleLogic, SubtitleError, VideoNotFoundError, SubtitlesUnavailableError, NetworkError, DependencyError
from ffmpeg_manager import FFmpegManager

# Set appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class SubtitleDownloaderGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("YouTube Subtitle Downloader Pro")
        self.geometry("700x800")

        self.logic = SubtitleLogic(logger=self)
        self.ffmpeg_mgr = FFmpegManager()
        
        # Grid Configuration
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(9, weight=1) # Log area grows

        # --- URL Section ---
        self.url_label = ctk.CTkLabel(self, text="URL Video YouTube / Short:", font=("Segoe UI", 14, "bold"))
        self.url_label.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")

        self.url_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.url_frame.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.url_frame.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(self.url_frame, placeholder_text="https://www.youtube.com/watch?v=...")
        self.url_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        
        self.paste_btn = ctk.CTkButton(self.url_frame, text="Incolla", width=80, command=self.paste_url)
        self.paste_btn.grid(row=0, column=1)

        # --- Options Section ---
        self.options_frame = ctk.CTkFrame(self)
        self.options_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.options_frame.grid_columnconfigure((0, 1), weight=1)

        # Language Selection
        self.lang_label = ctk.CTkLabel(self.options_frame, text="Lingua Sottotitoli:", font=("Segoe UI", 12))
        self.lang_label.grid(row=0, column=0, padx=15, pady=(10, 0), sticky="w")
        
        self.lang_combo = ctk.CTkComboBox(self.options_frame, values=["Inserisci URL e clicca 'Carica'..."])
        self.lang_combo.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="ew")
        self.lang_combo.set("Inserisci URL e clicca 'Carica'...")

        # Format Selection
        self.format_label = ctk.CTkLabel(self.options_frame, text="Formato File:", font=("Segoe UI", 12))
        self.format_label.grid(row=0, column=1, padx=15, pady=(10, 0), sticky="w")
        
        self.format_combo = ctk.CTkComboBox(self.options_frame, values=["srt", "vtt", "txt"])
        self.format_combo.grid(row=1, column=1, padx=15, pady=(0, 10), sticky="ew")
        self.format_combo.set("srt")

        # Source Filter
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

        # --- Destination Section ---
        self.dest_label = ctk.CTkLabel(self, text="Cartella di destinazione:", font=("Segoe UI", 14, "bold"))
        self.dest_label.grid(row=3, column=0, padx=20, pady=(10, 5), sticky="w")

        self.dest_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.dest_frame.grid(row=4, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.dest_frame.grid_columnconfigure(0, weight=1)

        self.dest_entry = ctk.CTkEntry(self.dest_frame)
        self.dest_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.dest_entry.insert(0, ".")
        
        self.browse_btn = ctk.CTkButton(self.dest_frame, text="Sfoglia", width=80, command=self.browse_folder)
        self.browse_btn.grid(row=0, column=1)

        # --- Actions Section ---
        self.action_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.action_frame.grid(row=7, column=0, padx=20, pady=10, sticky="ew")
        self.action_frame.grid_columnconfigure(0, weight=1)

        self.download_btn = ctk.CTkButton(self.action_frame, text="Scarica Sottotitoli", 
                                              font=("Segoe UI", 14, "bold"), height=40, border_width=0, command=self.start_download_thread)
        self.download_btn.grid(row=0, column=0, padx=0, pady=5, sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(self.action_frame)
        self.progress_bar.grid(row=1, column=0, padx=0, pady=5, sticky="ew")
        self.progress_bar.set(0)

        # --- Log Section ---
        self.log_label = ctk.CTkLabel(self, text="Log di sistema:", font=("Segoe UI", 12))
        self.log_label.grid(row=8, column=0, padx=20, pady=(10, 0), sticky="w")

        self.log_area = ctk.CTkTextbox(self, state='disabled', font=("Consolas", 12))
        self.log_area.grid(row=9, column=0, padx=20, pady=(0, 10), sticky="nsew")

        # --- FFmpeg Configuration Section ---
        self.ffmpeg_label = ctk.CTkLabel(self, text="Configurazione FFmpeg:", font=("Segoe UI", 14, "bold"))
        self.ffmpeg_label.grid(row=5, column=0, padx=20, pady=(20, 5), sticky="w")

        self.ffmpeg_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.ffmpeg_frame.grid(row=6, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.ffmpeg_frame.grid_columnconfigure(0, weight=1)

        # Version display
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

        # Initial version check
        self.refresh_ffmpeg_version()

        # --- Bottom Actions ---
        self.bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.bottom_frame.grid(row=10, column=0, padx=20, pady=(0, 20), sticky="ew")

        
        self.open_folder_btn = ctk.CTkButton(self.bottom_frame, text="Apri Cartella", 
                                            fg_color="#7f8c8d", hover_color="#95a5a6",
                                            command=self.open_dest_folder, state="disabled")
        self.open_folder_btn.pack(side="right")

    # --- Logic Methods ---

    def log(self, message):
        self.log_area.configure(state='normal')
        self.log_area.insert("end", message + "\n")
        self.log_area.see("end")
        self.log_area.configure(state='disabled')

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

    def refresh_ffmpeg_version(self):
        def task():
            version = self.ffmpeg_mgr.get_local_version()
            # Update UI from thread safely
            self.after(0, lambda: self.ffmpeg_ver_label.configure(text=f"Versione: {version or 'Sconosciuta'}"))
        
        threading.Thread(target=task, daemon=True).start()

    def update_ffmpeg(self):
        def task():
            self.log("Controllo aggiornamenti FFmpeg in corso...")
            update_info = self.ffmpeg_mgr.check_for_update()
            
            if update_info["update_available"]:
                msg = f"Nuova versione disponibile: {update_info['remote']} (Installata: {update_info['local']})\nVuoi aggiornare?"
                if messagebox.askyesno("Aggiornamento Disponibile", msg):
                    self.log("Download e installazione di FFmpeg in corso...")
                    success = self.ffmpeg_mgr.download_and_install(os.path.abspath("."))
                    if success:
                        self.log("FFmpeg aggiornato con successo!")
                        messagebox.showinfo("Successo", "FFmpeg è stato aggiornato all'ultima versione.")
                        self.after(0, self.refresh_ffmpeg_version)
                    else:
                        self.log("Errore durante l'aggiornamento di FFmpeg.")
                        messagebox.showerror("Errore", "Impossibile aggiornare FFmpeg automaticamente.")
                else:
                    self.log("Aggiornamento annullato dall'utente.")
            else:
                self.log(f"FFmpeg è già aggiornato (Versione: {update_info['local']}).")
                messagebox.showinfo("Info", "FFmpeg è già alla versione più recente.")

        threading.Thread(target=task, daemon=True).start()

    def open_dest_folder(self):

        path = self.dest_entry.get().strip() or "."
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            subprocess.run(['explorer', abs_path], shell=True)
        else:
            self.log("Errore: La cartella non esiste.")

    def load_languages(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Attenzione", "Per favore, inserisci prima l'URL del video.")
            return

        self.fetch_btn.configure(state="disabled", text="Caricamento...")
        
        def task():
            try:
                subs = self.logic.get_available_subtitles(url)
                if not subs:
                    self.log("Nessun sottotitolo disponibile per questo video.")
                    self.lang_combo.configure(values=["Nessuno disponibile"])
                    self.lang_combo.set("Nessuno disponibile")
                else:
                    # Create a list of display names (e.g., "Italiano (manual)")
                    display_list = [f"{s['name']} ({'man.' if s['type']=='manual' else 'auto'})" for s in subs]
                    self.lang_combo.configure(values=display_list)
                    self.lang_combo.set(display_list[0])
                    # Store the actual codes for mapping
                    self.current_subs_map = {f"{s['name']} ({'man.' if s['type']=='manual' else 'auto'})": s['lang'] for s in subs}
                    self.log(f"Trovate {len(subs)} lingue disponibili.")
            except SubtitleError as e:
                self.log(f"Errore caricamento lingue: {e}")
                messagebox.showerror("Errore", str(e))
            except Exception as e:
                self.log(f"Errore imprevisto: {e}")
                messagebox.showerror("Errore Critico", f"Si è verificato un errore imprevisto: {e}")
            finally:
                self.fetch_btn.configure(state="normal", text="Carica Lingue Disponibili")

        threading.Thread(target=task, daemon=True).start()

    def progress_hook(self, d):
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0%').replace('%', '')
            try:
                float_p = float(p) / 100.0
                self.progress_bar.set(float_p)
            except ValueError:
                pass
        elif d['status'] == 'finished':
            self.progress_bar.set(1.0)

    def start_download_thread(self):
        url = self.url_entry.get().strip()
        dest = self.dest_entry.get().strip() or "."
        fmt = self.format_combo.get()
        
        # Resolve selected language code
        selected_lang_text = self.lang_combo.get()
        if not hasattr(self, 'current_subs_map') or selected_lang_text not in self.current_subs_map:
            # Fallback to manual input if map is missing or selection is invalid
            # We allow users to manually type into the combo box (which CTK allows)
            lang = selected_lang_text
        else:
            lang = self.current_subs_map[selected_lang_text]

        if not url or not lang or lang == "Inserisci URL e clicca 'Carica'...":
            messagebox.showwarning("Attenzione", "Assicurati di aver inserito l'URL e selezionato una lingua.")
            return

        # Filters
        manual_only = not self.auto_var.get()
        auto_only = not self.manual_var.get()
        
        if manual_only and auto_only:
             messagebox.showwarning("Attenzione", "Seleziona almeno un tipo di sottotitolo (Manuale o Automatico).")
             return

        self.download_btn.configure(state="disabled")
        self.open_folder_btn.configure(state="disabled")
        self.progress_bar.set(0)
        
        def task():
            try:
                result_path = self.logic.download_subtitles(
                    url=url, 
                    lang=lang, 
                    dest=dest, 
                    format=fmt, 
                    auto_only=auto_only, 
                    manual_only=manual_only, 
                    progress_hook=self.progress_hook
                )
                self.log(f"Completato! File salvati in: {result_path}")
                self.open_folder_btn.configure(state="normal")
                messagebox.showinfo("Successo", "Sottotitoli scaricati con successo!")
            except VideoNotFoundError as e:
                self.log(f"ERRORE: {e}")
                messagebox.showerror("Video non trovato", str(e))
            except SubtitlesUnavailableError as e:
                self.log(f"ERRORE: {e}")
                messagebox.showerror("Sottotitoli non disponibili", str(e))
            except NetworkError as e:
                self.log(f"ERRORE DI RETE: {e}")
                messagebox.showerror("Errore di Rete", str(e))
            except DependencyError as e:
                self.log(f"ERRORE DIPENDENZE: {e}")
                messagebox.showerror("Errore Dipendenze", str(e))
            except SubtitleError as e:
                self.log(f"ERRORE: {e}")
                messagebox.showerror("Errore", str(e))
            except Exception as e:
                self.log(f"ERRORE CRITICO: {e}")
                messagebox.showerror("Errore Critico", f"Si è verificato un errore imprevisto:\n{e}")
            finally:
                self.download_btn.configure(state="normal")
                self.focus() # Remove focus from button to avoid visual artifacts (black line)

        threading.Thread(target=task, daemon=True).start()

if __name__ == "__main__":
    app = SubtitleDownloaderGUI()
    app.mainloop()