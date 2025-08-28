import logging
from pathlib import Path
from typing import Optional


class _PrefixAdapter(logging.LoggerAdapter):
    def __init__(self, logger: logging.Logger, prefix: str):
        super().__init__(logger, {})
        self.prefix = prefix

    def process(self, msg, kwargs):
        return f"[{self.prefix}] {msg}", kwargs


def setup_logging(cfg: dict, log_file: Optional[Path] = None) -> None:
    """Configure root logging according to config.yaml."""
    runtime = cfg.get("runtime", {})
    level_name = str(runtime.get("log_level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if runtime.get("log_to_file", False):
        file_path = log_file or Path("app.log")
        handlers.append(logging.FileHandler(file_path, encoding="utf-8"))

    logging.basicConfig(level=level, handlers=handlers, format="%(message)s")


def get_logger(prefix: str) -> logging.LoggerAdapter:
    """Return a logger that automatically prefixes messages."""
    logger = logging.getLogger(prefix)
    return _PrefixAdapter(logger, prefix)
