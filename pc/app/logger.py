"""Logging helpers used across the application."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional, Union

from config_models import AppConfig, RuntimeConfig


class _PrefixAdapter(logging.LoggerAdapter):
    def __init__(self, logger: logging.Logger, prefix: str):
        super().__init__(logger, {})
        self.prefix = prefix

    def process(
        self, msg: str, kwargs: MutableMapping[str, Any]
    ) -> tuple[str, MutableMapping[str, Any]]:
        return f"[{self.prefix}] {msg}", kwargs


def _ensure_runtime_config(
    cfg: Union[AppConfig, RuntimeConfig, Mapping[str, Any]]
) -> RuntimeConfig:
    if isinstance(cfg, AppConfig):
        return cfg.runtime
    if isinstance(cfg, RuntimeConfig):
        return cfg
    runtime = cfg.get("runtime", {}) if isinstance(cfg, Mapping) else {}
    return RuntimeConfig.from_mapping(runtime)


def setup_logging(
    cfg: Union[AppConfig, RuntimeConfig, Mapping[str, Any]],
    log_file: Optional[Path] = None,
) -> None:
    """Configure root logging according to config.yaml."""

    runtime = _ensure_runtime_config(cfg)
    level_name = str(runtime.log_level).upper()
    level = getattr(logging, level_name, logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if runtime.log_to_file:
        file_path = log_file or Path("app.log")
        handlers.append(logging.FileHandler(file_path, encoding="utf-8"))

    logging.basicConfig(level=level, handlers=handlers, format="%(message)s")


def get_logger(prefix: str) -> logging.LoggerAdapter:
    """Return a logger that automatically prefixes messages."""
    logger = logging.getLogger(prefix)
    return _PrefixAdapter(logger, prefix)
