"""Safe, small YAML configuration loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when the configuration file cannot be used."""


class Config:
    def __init__(self, filename: str | Path = "config.yaml") -> None:
        self.filename = Path(filename)
        if not self.filename.is_file():
            raise ConfigError(f"Configuration file not found: {self.filename}")
        try:
            with self.filename.open("r", encoding="utf-8") as file:
                self.data = yaml.safe_load(file) or {}
        except yaml.YAMLError as error:
            raise ConfigError(f"Invalid YAML in {self.filename}: {error}") from error
        if not isinstance(self.data, dict):
            raise ConfigError("The configuration root must be a mapping.")

    def get(self, section: str, key: str | None = None, default: Any = None) -> Any:
        value = self.data.get(section, default)
        if key is None:
            return value
        return value.get(key, default) if isinstance(value, dict) else default
