from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(logs_dir: Path) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "dictado_ai.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    file_handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    _install_exception_hooks()
    return log_file


def _install_exception_hooks() -> None:
    import sys
    import threading

    def handle_sys_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.getLogger("dictado_ai.crash").critical(
            "Excepción no capturada en hilo principal:",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    def handle_threading_exception(args: threading.ExceptHookArgs):
        if issubclass(args.exc_type, KeyboardInterrupt):
            return
        logging.getLogger("dictado_ai.crash").critical(
            "Excepción no capturada en hilo '%s':",
            args.thread.name if args.thread else "desconocido",
            exc_info=(args.exc_type, args.exc_value, args.exc_tb),
        )

    sys.excepthook = handle_sys_exception
    threading.excepthook = handle_threading_exception

