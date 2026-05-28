# YouTube Subtitle Downloader

Questo programma permette di scaricare i sottotitoli (sia manuali che automatici) da un video di YouTube o da YouTube Shorts, senza dover scaricare l'intero file video.

## Requisiti

Il programma richiede:
1. **Python** installato sul sistema.
2. **Node.js (JS Runtime)**: Utilizzato da `yt-dlp` per l'estrazione dei dati. Il programma tenterà di installarlo automaticamente tramite Chocolatey se non viene trovato nel sistema.

*Nota: Non è più necessario installare FFmpeg manualmente; il programma lo scaricherà e configurerà automaticamente al primo avvio.*

## Installazione

1. Apri il terminale nella cartella del progetto.
2. Installa la libreria necessaria utilizzando pip:

```bash
pip install -r requirements.txt
```

## Utilizzo

**Nota per il primo avvio:** Al primo avvio (o se i componenti sono mancanti), il programma scaricherà automaticamente i binari di **FFmpeg** (circa 100MB) e tenterà di configurare il runtime JavaScript. Assicurati di avere una connessione internet attiva.

Avvia l'interfaccia grafica con il seguente comando:

```bash
python download_subs.py
```

Si aprirà una finestra dove potrai:
1. Inserire l'**URL del video** di YouTube o Short (puoi usare il tasto **"Incolla"** per inserirlo rapidamente dalla clipboard).
2. Scegliere il **codice della lingua** (es. `it` per italiano, `en` per inglese, `uk` per ucraino).
3. Selezionare la **cartella di destinazione** tramite il tasto "Sfoglia".
4. Monitorare l'avanzamento del processo direttamente nel **Log del programma** integrato nella finestra.

I sottotitoli verranno salvati in formato `.srt` con il nome del video nella cartella scelta.

## Compilazione in Eseguibile (.exe)

Per trasformare il programma in un file eseguibile per Windows, puoi utilizzare **PyInstaller**.

1. Installa PyInstaller:
```bash
pip install pyinstaller
```

2. Esegui il comando di impacchettamento (include i binari di FFmpeg all'interno dell'exe):
```bash
pyinstaller --noconsole --onefile --add-data "ffmpeg.exe;." --add-data "ffplay.exe;." --add-data "ffprobe.exe;." download_subs.py
```

Il file eseguibile verrà generato nella cartella `dist/`.
