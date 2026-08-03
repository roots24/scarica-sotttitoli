"""Modulo per la gestione della configurazione dell'applicazione."""

import json
import os
import threading
from typing import Optional

from ffmpeg_manager import get_app_dir


class AppConfig:
    """Gestisce le impostazioni dell'app (retry, ecc.) persistite in config.json."""

    DEFAULT_RETRY_ATTEMPTS = 2
    DEFAULT_RETRY_DELAY = 2.0  # secondi

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or os.path.join(get_app_dir(), "config.json")
        self._lock = threading.Lock()
        self._config = self._load_config()

    def _load_config(self) -> dict:
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_config(self) -> None:
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=4)
        except Exception as e:
            print(f"Errore salvataggio config app: {e}")

    @property
    def retry_attempts(self) -> int:
        with self._lock:
            return self._config.get("retry_attempts", self.DEFAULT_RETRY_ATTEMPTS)

    @retry_attempts.setter
    def retry_attempts(self, value: int) -> None:
        if not isinstance(value, int) or value < 0:
            raise ValueError("I tentativi di retry devono essere un intero >= 0")
        with self._lock:
            self._config["retry_attempts"] = value
            self._save_config()

    @property
    def retry_delay(self) -> float:
        with self._lock:
            return self._config.get("retry_delay", self.DEFAULT_RETRY_DELAY)

    @retry_delay.setter
    def retry_delay(self, value: float) -> None:
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError("Il delay di retry deve essere un numero >= 0")
        with self._lock:
            self._config["retry_delay"] = value
            self._save_config()
