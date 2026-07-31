# AGENTS.md

YouTube Subtitle Downloader Pro — Windows-only Python desktop app (customtkinter) that downloads YouTube subtitles via yt-dlp and converts to `.srt`/`.vtt`/`.txt` with FFmpeg. All user-facing UI strings, log messages, and exceptions are **Italian** — keep them that way.

## Commands

- Run: `python gui.py` (from the repo root; paths are now resolved relative to the script, but the `dist/` build and `ffmpeg/` install land next to the script dir)
- Deps: `pip install -r requirements.txt` (only `yt-dlp` and `customtkinter`)
- Dev deps: `pip install -r requirements-dev.txt` (`pytest`, `ruff`, `pyinstaller`)
- Test: `python -m pytest tests -q` (logic and ffmpeg_manager are headless-testable; the GUI itself cannot be exercised headless)
- Lint: `python -m ruff check .` (config in `pyproject.toml`, line-length 120)
- Build exe: `pyinstaller gui.spec` → `dist/gui.exe` (gui.spec locates the customtkinter data path automatically from the build environment, no hardcoded paths; `build/` and `dist/` are git-ignored, FFmpeg is NOT bundled — the app downloads it into `ffmpeg/bin/` on first run)
- CI: `.github/workflows/ci.yml` runs ruff + pytest on Windows (Python 3.11/3.13)

## Architecture

- `gui.py` — entry point. UI + threading: all background work runs in daemon threads; UI updates must go through `self.after(0, ...)`, never from worker threads. Passes itself as `logger` to logic.
- `logic.py` — `SubtitleLogic`: yt-dlp interaction, dependency checks, download + conversion. Error contract: custom hierarchy `SubtitleError` → `VideoNotFoundError` / `SubtitlesUnavailableError` / `NetworkError` / `DependencyError`; the GUI catches these types and shows specific message boxes — keep these imports in sync if you touch exceptions. Exposes `is_ytdlp_breakage()` (used by the GUI to suggest `pip install -U yt-dlp`).
- `ffmpeg_manager.py` — `FFmpegManager`: auto-downloads FFmpeg (BtbN win64-gpl-shared build, ~100MB) into `ffmpeg/bin/`, persists the path in `config.json`. Paths are resolved via `get_app_dir()` (script/exe dir, frozen-aware) — keep them CWD-independent.
- `tests/` — pytest suite with mocked `yt_dlp.YoutubeDL` and `FFmpegManager` (no network, no GUI). Run after any logic change.

## Gotchas

- `config.json` is runtime state (machine-specific absolute FFmpeg path) — rewritten at runtime by the app, **not tracked in git** (see `.gitignore`); `build/`, `dist/`, `ffmpeg/` binaries are also untracked.
- `yt-dlp` breaks whenever YouTube changes; the app checks PyPI at startup and the GUI suggests `pip install -U yt-dlp` on typical breakage errors.
- `ensure_dependencies()` tries `choco install nodejs -y` if Node isn't found; Node is passed to yt-dlp as `js_runtimes`. Keep that fallback logic intact.
- `logic.download_subtitles` handles `txt` by converting to `srt` (yt-dlp has no txt support); final file-match check is a substring match on the slugified title in the dest folder.
- `gui.py` uses `get_program_dir()` for PyInstaller frozen mode — keep frozen-awareness in path logic.
- URL validation lives in `gui.py` (`is_valid_youtube_url`), not in logic.

## Roadmap

- `PLAN.md` — phased improvement plan (phases 0-3, all completed; "Idee future" section lists non-planned ideas). Update it when scope changes.
