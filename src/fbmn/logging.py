import logging
import re
import sys
import os
from pythonjsonlogger import json

# ANSI color codes (optional, only for local dev console)
COLORS = {
    "R": "\033[31m",  # Red
    "G": "\033[32m",  # Green
    "Y": "\033[33m",  # Yellow
    "B": "\033[34m",  # Blue
    "M": "\033[35m",  # Magenta
    "C": "\033[36m",  # Cyan
    "W": "\033[37m",  # White
}
RESET = "\033[0m"

# Regex: matches $X$ followed by text
pattern = re.compile(r"\$([A-Z])\$(.*?)((?=\$[A-Z]\$)|$)")

USE_COLORS = os.getenv("USE_COLORS", "0") == "1"


def colorize(text: str) -> str:
    """Replace $X$text-style markup with ANSI color codes."""
    def replacer(match):
        code = match.group(1)
        content = match.group(2)
        color = COLORS.get(code, "")
        return f"{color}{content}{RESET}" if USE_COLORS else content

    return pattern.sub(replacer, text)


class JSONFormatter(json.JsonFormatter):
    """JSON formatter with optional inline color parsing."""

    def process_log_record(self, log_record):
        raw_message = str(log_record.get("message", ""))
        # Use colored text only if enabled (otherwise plain)
        log_record["message"] = colorize(raw_message)
        return super().process_log_record(log_record)


def get_logger(name: str, level=logging.DEBUG) -> logging.Logger:
    """Factory to create configured loggers."""
    json_handler = logging.StreamHandler(sys.stdout)
    json_handler.setFormatter(
        JSONFormatter("{asctime}{levelname}{message}", style="{")
    )

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()
    logger.addHandler(json_handler)
    logger.propagate = False
    return logger


# Example setup
logger = get_logger("discord_bot", logging.DEBUG)
discord_logger = get_logger("discord", logging.WARNING)