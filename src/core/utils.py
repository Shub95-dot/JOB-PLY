"""Shared utility functions: logging, retries, text parsing, and file loading."""

import os
import sys
import logging
import time
import re
from typing import Callable, Any, Type, Tuple, Dict
import yaml


def setup_logger(
    name: str = "job_app_agent",
    log_dir: str = "logs",
    app_log_filename: str = "applications.log",
    error_log_filename: str = "errors.log",
    level: int = logging.INFO
) -> logging.Logger:
    """Configures and returns a logger instance with console and file handlers."""
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers if already configured
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Applications Log Handler (INFO + DEBUG)
    app_log_path = os.path.join(log_dir, app_log_filename)
    app_handler = logging.FileHandler(app_log_path, encoding="utf-8")
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(formatter)
    logger.addHandler(app_handler)

    # Errors Log Handler (ERROR + CRITICAL)
    error_log_path = os.path.join(log_dir, error_log_filename)
    error_handler = logging.FileHandler(error_log_path, encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    return logger


def retry(
    max_retries: int = 3,
    backoff_factor: float = 1.5,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
) -> Callable:
    """Decorator to retry a function with exponential backoff."""
    def decorator(func: Callable) -> Callable:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            retries = 0
            delay = 1.0
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    if retries > max_retries:
                        raise e
                    time.sleep(delay)
                    delay *= backoff_factor
        return wrapper
    return decorator


def count_words(text: str) -> int:
    """Count words in a string, stripping punctuation."""
    if not text:
        return 0
    words = re.findall(r'\b\w+\b', text)
    return len(words)


def clean_text(text: str) -> str:
    """Clean and normalize whitespace in text."""
    if not text:
        return ""
    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def load_yaml(file_path: str) -> Dict[str, Any]:
    """Safely load a YAML configuration file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
