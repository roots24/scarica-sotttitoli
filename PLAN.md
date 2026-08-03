# Piano di miglioramento

Roadmap per il miglioramento di YouTube Subtitle Downloader Pro. Le fasi sono ordinate per priorità (impatto/costo/rischio).

## Fase 0 — Quick win ✅ (completata)

1. ✅ **`build/` e `dist/` fuori da git** — aggiunto `.gitignore` per gli artifact PyInstaller, `config.json` (path assoluti di macchina), i binari `ffmpeg/` e `__pycache__/`; file rimossi dall'indice git
2. ✅ **Path CWD-indipendenti** — `ffmpeg_manager.py` usa `get_app_dir()` (dir dello script/eseguibile) per `config.json`, default FFmpeg e installazione, invece di `os.path.abspath(".")`
3. ✅ **Rimosso `download_subs.py`** — logica duplicata e morta, eliminato dal repo
4. ✅ **Suggerimento "aggiorna yt-dlp" nel GUI** — `is_ytdlp_breakage()` rileva errori tipici di yt-dlp obsoleto e logga il consiglio `pip install -U yt-dlp`

## Fase 1 — Refactor per testabilità ✅ (completata)

5. ✅ **Separate le responsabilità in `logic.py`** — estratti `_build_ydl_opts(...)`, `_find_matching_file(...)`, `_map_ytdlp_error(...)`, `_fetch_available_subtitles(...)`; `convert_vtt_to_srt` già isolata
6. ✅ **Unit test con pytest** — `tests/test_logic.py` (12 test) e `tests/test_ffmpeg_manager.py` (9 test) con mock di `yt_dlp.YoutubeDL` e `FFmpegManager`; `requirements-dev.txt` con `pytest` e `ruff`; `conftest.py` per il path di import
7. ✅ **Mappatura errori robusta** — `_map_ytdlp_error` usa `exc_info` (HTTPError 404) prima del fallback su substring; fix anche della verifica finale per `txt` (prima cercava `.vtt` e falliva sempre)

## Fase 2 — Affidabilità ✅ (completata)

8. ✅ **Retry con backoff** — `_with_retry` (2 tentativi, 2s) su `get_available_subtitles` in caso di `NetworkError`
9. ✅ **Timeout su download FFmpeg** — `_download_zip` con `urlopen(timeout=60)` e pulizia file parziali; timeout 15s sull'API GitHub; pulizia zip corrotto
10. ✅ **Check versione yt-dlp all'avvio** — `check_ytdlp_update()` confronta con PyPI e avvisa nel log del GUI

## Fase 3 — Qualità e processo ✅ (completata)

11. ✅ **CI GitHub Actions** — `.github/workflows/ci.yml`: ruff + pytest su Windows (Python 3.11/3.13)
12. ✅ **Lint + type hints** — `pyproject.toml` con config ruff (line-length 120, regole E4/E7/E9/F/I); tipizzate le firme pubbliche di `logic.py` e `ffmpeg_manager.py`; rimosso codice morto (`get_resource_path`)
13. ✅ **Lingua uniforme (IT)** — docstring e commenti convertiti in italiano in `gui.py`, `logic.py`, `ffmpeg_manager.py`
14. ✅ **UX** — timestamp `[HH:MM:SS]` nei log, validazione URL YouTube prima di fetch/download, pulsante download disabilitato durante "Carica Lingue"

## Fase 4 — Indurimento ✅ (completata)

15. ✅ **Istanza FFmpegManager condivisa** — `SubtitleLogic` accetta `ffmpeg_mgr` nel costruttore; la GUI passa la stessa istanza, eliminando la sync manuale di `ffmpeg_path` e la race teorica tra thread
16. ✅ **Validazione codice lingua manuale** — input manuale nella combo validato con regex ISO (es. `it`, `pt-BR`), con log esplicativo; niente più passaggio cieco di testo arbitrario a yt-dlp
17. ✅ **Falsi positivi ridotti in `is_ytdlp_breakage`** — marker `Unsupported` → `Unsupported URL` (niente più trigger su "Unsupported protocol"); test aggiunti
18. ✅ **Node.js cross-platform** — `where node` sostituito con `shutil.which("node")` (mantiene il fallback choco su Windows)
19. ✅ **Lock su `set_ffmpeg_path`** — accesso concorrente al path/config protetto da `threading.Lock`

## Fase 5 — Playlist e coda ✅ (completata)

20. ✅ **Supporto playlist** — `download_subtitles` gestisce URL playlist: `_iter_entries()` estrae gli entries e processa ogni video; un file mancante in playlist logga e continua, ma se nessun video ha sottotitoli viene sollevato `SubtitlesUnavailableError`
21. ✅ **Coda di download multipli** — la GUI accetta più URL (uno per riga); `download_queue()` in `logic.py` li processa in sequenza continuando dopo un errore, con conteggio finale successi/errori; `load_languages` unisce le lingue da tutti gli URL

## Fase 6 — Configurazione ✅ (completata)

22. ✅ **Retry configurabile dall'UI** — `config.py` (`AppConfig`, prima codice morto) ora usato da `SubtitleLogic`: `_with_retry` legge `retry_attempts`/`retry_delay` persistiti in `config.json`; nuova sezione "Impostazioni Retry" nel tab Impostazioni della GUI; `AppConfig` reso frozen-aware via `get_app_dir()`

## Fase 7 — Dipendenze ✅ (completata)

23. ✅ **`urllib.request` sostituito con `requests`** — `ffmpeg_manager.py` (`_download_zip` con streaming a chunk, `get_remote_version` con timeout 15s) e `logic.py` (`check_ytdlp_update`); `requests` aggiunto a `requirements.txt`; rimossi import inutilizzati

## Fase 8 — Audit e bugfix ✅ (completata)

24. ✅ **`js_runtimes` funzionante** — `logic.py` passava `{'Node': {'executable': ...}}`: yt-dlp accetta solo chiavi minuscole (`node`) e lo schema `{'path': ...}`, quindi Node veniva silenziosamente scartato. Corretto in `{'node': {'path': node_path}}` (verificato sul sorgente yt-dlp 2026.07.04)
25. ✅ **`get_remote_version` riparato** — gli asset BtbN non contengono mai `ffmpeg-<x.y.z>` (sono `ffmpeg-master-latest-...` o `ffmpeg-n8.1-latest-win64-gpl-shared-8.1.zip`): la vecchia regex non matchava mai e "Aggiorna FFmpeg" non funzionava. Ora estrae la versione più alta dagli asset con versione; confronto numerico (`version_tuple`, componenti mancanti riempite con zeri: `'8.1' == '8.1.0'`) invece che lessicografico; le build master (versione non parsabile) non generano più falsi inviti all'installazione
26. ✅ **Filtro "Automatici" ora efficace** — con entrambi i filtri attivi yt-dlp scaricava solo i manuali per le lingue che li hanno (comportamento `process_subtitles`). Ora doppia passata: manuali prima, poi automatici con suffisso `.auto` nel nome (`Titolo.auto.en.vtt`) per evitare collisioni
27. ✅ **Thread-safety tkinter** — `messagebox` e `configure()` venivano chiamati dai thread worker: ora tutti gli aggiornamenti UI (esito download, caricamento lingue, aggiornamento FFmpeg) passano dal main thread via `self.after(0, ...)` con helper dedicati (`_on_download_*`, `_set_languages`, `_handle_ffmpeg_update_info`); risolto anche il late-binding delle lambda (`lambda e=e:`)
28. ✅ **Formato `txt` reale** — prima selezionare "txt" produceva comunque file `.srt`. Ora `convert_srt_to_txt()` estrae il solo testo (via postprocessor srt di yt-dlp, rimuovendo indici e timestamp) e produce veri `.txt`
29. ✅ **Niente falsi successi con file stantii** — il match dei file è ora esatto (`<slug>.<lang>.<ext>`) e confrontato con uno snapshot pre-run della cartella di destinazione: un `.srt` di un download precedente non conta più come successo né viene convertito/cancellato
30. ✅ **Versioni yt-dlp dev/nightly** — `check_ytdlp_update` usa il confronto numerico: una nightly più nuova della stabile PyPI non viene più segnalata come obsoleta
31. ✅ **`load_languages` non riabilita il download durante un download attivo** — il `finally` rispetta `is_downloading`
32. ✅ **README corretto** — i path di `config.json`/`ffmpeg/` sono risolti rispetto alla dir dello script, non alla CWD

## Idee future (non pianificate)

- Nessuna al momento.

## Priorità

| Fase | Impatto | Costo | Rischio | Stato |
|---|---|---|---|---|
| 0 (1–4) | Alto (igiene repo + bug CWD) | Basso | Nullo | ✅ |
| 1 (5–7) | Alto (prevenzione regressioni) | Medio | Basso | ✅ |
| 2 (8–10) | Medio (stabilità runtime) | Medio | Basso | ✅ |
| 3 (11–14) | Medio (mantenibilità) | Medio | Basso | ✅ |
| 4 (15–19) | Medio (robustezza) | Basso | Basso | ✅ |
| 5 (20–21) | Alto (funzionalità playlist + batch) | Medio | Medio | ✅ |
| 6 (22) | Medio (usabilità) | Basso | Basso | ✅ |
| 7 (23) | Basso (manutenibilità) | Basso | Basso | ✅ |
| 8 (24–32) | Alto (funzionalità + stabilità) | Medio | Basso | ✅ |
