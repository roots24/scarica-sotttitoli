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

## Idee future (non pianificate)

- Supporto playlist (più video per URL)
- Coda di download multipli
- Ripetizione del retry configurabile dall'UI
- Sostituire `urllib.request` con `requests` (più gestibile, ma aggiunge dipendenza)

## Priorità

| Fase | Impatto | Costo | Rischio | Stato |
|---|---|---|---|---|
| 0 (1–4) | Alto (igiene repo + bug CWD) | Basso | Nullo | ✅ |
| 1 (5–7) | Alto (prevenzione regressioni) | Medio | Basso | ✅ |
| 2 (8–10) | Medio (stabilità runtime) | Medio | Basso | ✅ |
| 3 (11–14) | Medio (mantenibilità) | Medio | Basso | ✅ |
