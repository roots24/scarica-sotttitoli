# Guida all'Installazione e Configurazione - YouTube Subtitle Downloader Pro

## 🛠 Analisi Tecnica dell'Architettura
Il **YouTube Subtitle Downloader Pro** è progettato seguendo un'architettura a tre livelli per garantire modularità, manutenibilità e facilità di distribuzione.

### 1. Livello Interfaccia Utente (GUI Layer) - `gui.py`
L'interfaccia è sviluppata utilizzando **customtkinter**, una libreria che estende Tkinter per fornire un look moderno e coerente con i sistemi operativi attuali.
- **Asincronia**: Tutte le operazioni pesanti (download, ricerca lingue, aggiornamenti FFmpeg) sono eseguite in thread separati per evitare il blocco della GUI (*main loop*).
- **Interazione**: Gestisce l'input dell'utente, la visualizzazione dei log di sistema e il feedback visivo tramite una barra di progresso.

### 2. Livello Logica Core (Core Logic Layer) - `logic.py`
Questo livello funge da orchestratore tra l'interfaccia e le dipendenze esterne.
- **Integrazione yt-dlp**: Utilizza la potente libreria `yt-dlp` per l'estrazione dei metadati del video e il download dei sottotitoli (sia manuali che generati automaticamente).
- **Gestione Flussi**: Implementa un sistema di eccezioni personalizzate (`SubtitleError`, `NetworkError`, ecc.) per comunicare errori specifici alla GUI.
- **Post-Processing**: Coordina la conversione dei formati (WebVTT $\rightarrow$ SRT) interfacciandosi con il livello FFmpeg.

### 3. Livello Gestione FFmpeg (FFmpeg Management Layer) - `ffmpeg_manager.py`
Un modulo specializzato per l'astrazione dell'estensione binaria necessaria alla conversione dei file.
- **Automazione**: Verifica la presenza di FFmpeg nel sistema; in caso di assenza, scarica automaticamente l'ultima build stabile da GitHub (BtbN).
- **Configurazione**: Gestisce la persistenza del percorso dell'eseguibile tramite un file `config.json`.
- **Versioning**: Confronta la versione locale con quella remota per notificare l'utente sulla disponibilità di aggiornamenti.

---

## 🚀 Guida all'Installazione (Sviluppo)

### Requisiti di Sistema
- **Python**: Versione 3.8 o superiore.
- **Sistema Operativo**: Windows 10/11 (raccomandato).

### Passaggi per l'installazione
1. Clona o scarica la cartella del progetto.
2. Apri il terminale nella directory principale.
3. Installa le dipendenze necessarie tramite pip:
   ```bash
   pip install -r requirements.txt
   ```
4. Avvia l'applicazione:
   ```bash
   python gui.py
   ```

---

## 📦 Istruzioni per il Packaging (.exe)

Per distribuire l'applicazione come un singolo file eseguibile per Windows, si raccomanda l'utilizzo di **PyInstaller**.

### Comando di Compilazione
Esegui il seguente comando nel terminale (PowerShell):
```powershell
$ctk_path = python -c "import customtkinter; import os; print(os.path.dirname(customtkinter.__file__))"; pyinstaller --noconsole --onefile --add-data "$($ctk_path);customtkinter/" gui.py
```

### Dettagli Tecnici dei Flag:
- `--noconsole`: Impedisce l'apertura della finestra del terminale (CMD) all'avvio dell'app, mostrando solo la GUI.
- `--onefile`: Impacchetta tutto in un unico file `.exe` per facilitare la distribuzione.
- `--add-data`: **Fondamentale**. `customtkinter` richiede i suoi file di temi e asset (JSON, immagini) per renderizzare l'interfaccia correttamente. Il comando PowerShell sopra indicato rileva automaticamente il percorso della libreria nel tuo ambiente Python.

### Gestione dei Binari FFmpeg
L'eseguibile creato non include FFmpeg al suo interno per evitare dimensioni eccessive. L'applicazione gestirà automaticamente:
1. La ricerca di un'installazione esistente.
2. Il download automatico nella cartella `/ffmpeg` relativa all'eseguibile al primo avvio o tramite il pulsante "Aggiorna FFmpeg".

Se desideri includere FFmpeg nel pacchetto, dovrai aggiungere la cartella `ffmpeg/` tramite l'opzione `--add-data` di PyInstaller e modificare `ffmpeg_manager.py` per leggere i file dalla directory temporanea di PyInstaller (`sys._MEIPASS`).