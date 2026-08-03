# AGENTS.md

YouTube Subtitle Downloader Pro — Windows-only Python desktop app (customtkinter) that downloads YouTube subtitles via yt-dlp and converts to `.srt`/`.vtt`/`.txt` with FFmpeg. All user-facing UI strings, log messages, and exceptions are **Italian** — keep them that way.

## Commands

- Run: `python gui.py` (from the repo root; paths are now resolved relative to the script, but the `dist/` build and `ffmpeg/` install land next to the script dir)
- Deps: `pip install -r requirements.txt` (`yt-dlp`, `customtkinter`, `requests`)
- Dev deps: `pip install -r requirements-dev.txt` (`pytest`, `ruff`, `pyinstaller`)
- Test: `python -m pytest tests -q` (logic and ffmpeg_manager are headless-testable; the GUI itself cannot be exercised headless)
- Lint: `python -m ruff check .` (config in `pyproject.toml`, line-length 120)
- Build exe: `python -m PyInstaller gui.spec` (or `pyinstaller gui.spec` if on PATH) → `dist/gui.exe` (gui.spec locates the customtkinter data path automatically from the build environment, no hardcoded paths; `build/` and `dist/` are git-ignored, FFmpeg is NOT bundled — the app downloads it into `ffmpeg/bin/` on first run)
- CI: `.github/workflows/ci.yml` runs ruff + pytest on Windows (Python 3.11/3.13)

## Architecture

- `gui.py` — entry point. UI + threading: all background work runs in daemon threads; UI updates (log, messagebox, widget state) must go through `self.after(0, ...)`, never from worker threads — even `messagebox` calls are routed via the `_on_download_*`/`_handle_ffmpeg_update_info`/`_set_languages` helpers on the main thread. Passes itself as `logger` to logic. The URL field accepts **one URL per line** (multi-URL queue); language loading unions languages from all URLs; a single URL still shows per-error message boxes, multi-URL shows a final summary.
- `logic.py` — `SubtitleLogic`: yt-dlp interaction, dependency checks, download + conversion. Error contract: custom hierarchy `SubtitleError` → `VideoNotFoundError` / `SubtitlesUnavailableError` / `NetworkError` / `DependencyError`; the GUI catches these types and shows specific message boxes — keep these imports in sync if you touch exceptions. Exposes `is_ytdlp_breakage()` (used by the GUI to suggest `pip install -U yt-dlp`). `download_subtitles` also handles **playlist URLs** (iterates `info["entries"]` via `_iter_entries()`, logs and continues on missing files); `download_queue(urls, ...)` processes a list of URLs sequentially and returns `{"successi": n, "errori": m}`. **Two-pass logic**: with both "Manuali" and "Automatici" filters selected, `download_subtitles` runs two yt-dlp passes (manual first, then auto with the `.auto` outtmpl suffix, e.g. `Titolo.auto.en.vtt`) so automatic captions don't overwrite manual ones; single-type selection keeps the plain `Titolo.en.<ext>` names. Node.js is passed to yt-dlp as `js_runtimes = {'node': {'path': node_path}}` (lowercase key — yt-dlp ignores unsupported runtime keys and expects `path`, not `executable`).
- `config.py` — `AppConfig`: persists app settings (`retry_attempts`, `retry_delay`) in `config.json`, thread-safe with a lock. `SubtitleLogic._with_retry` reads retry values from it (defaults: 2 attempts, 2s); the GUI edits them in the "Impostazioni" tab. Frozen-aware via `get_app_dir()` — same pattern as the other modules.
- `ffmpeg_manager.py` — `FFmpegManager`: auto-downloads FFmpeg (BtbN win64-gpl-shared build, ~100MB) into `ffmpeg/bin/`, persists the path in `config.json`. Paths are resolved via `get_app_dir()` (script/exe dir, frozen-aware) — keep them CWD-independent. Network calls use `requests` (streaming download, timeouts).
- `tests/` — pytest suite with mocked `yt_dlp.YoutubeDL` and `FFmpegManager` (no network, no GUI). Run after any logic change.

## Gotchas

- `config.json` is runtime state (machine-specific FFmpeg path + retry settings) — rewritten at runtime by the app, **not tracked in git** (see `.gitignore`); `build/`, `dist/`, `ffmpeg/` binaries are also untracked.
- `yt-dlp` breaks whenever YouTube changes; the app checks PyPI at startup and the GUI suggests `pip install -U yt-dlp` on typical breakage errors.
- `ensure_dependencies()` tries `choco install nodejs -y` if Node isn't found; Node is passed to yt-dlp as `js_runtimes = {'node': {'path': ...}}` — lowercase key and `path` (not `executable`): yt-dlp warns and silently drops unsupported runtime keys. Keep that fallback logic intact.
- yt-dlp has **no native txt support**: `logic` requests `.srt` via the `FFmpegSubtitlesConvertor` postprocessor and then `convert_srt_to_txt()` strips indices and timestamps into a real `.txt`, removing the `.srt`. Final file-match check is an **exact** name match (`<slug>.<lang>.<ext>`, e.g. `Titolo.en.srt`) against a pre-run snapshot of the dest folder (`_snapshot_dir`), so stale files from previous downloads never count as success. The snapshot records `(mtime_ns, size)` per file, NOT just names: a stale file **overwritten by the current run** (e.g. re-downloading the same video) counts as success, while an untouched stale file doesn't. Playlist URL = every entry processed with the same language/filter options.
- With both "Manuali" and "Automatici" filters selected the auto pass names files `Titolo.auto.en.<ext>` (`.auto` outtmpl suffix) — do not remove it, it prevents yt-dlp from overwriting the manual file of the same language.
- `gui.py` uses `get_program_dir()` for PyInstaller frozen mode — keep frozen-awareness in path logic.
- URL validation lives in `gui.py` (`is_valid_youtube_url`), applied per line in the multi-URL field, not in logic.

## Roadmap

- `PLAN.md` — phased improvement plan (phases 0-7, all completed; "Idee future" currently empty). Update it when scope changes.
