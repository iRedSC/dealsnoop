import logging
import re
import sys
from pythonjsonlogger import json

# ANSI color codes (optional, for local dev console)
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


def colorize(text: str) -> str:
    """Replace $X$text-style markup with ANSI color codes."""
    def replacer(match):
        code = match.group(1)
        content = match.group(2)
        color = COLORS.get(code, "")
        return f"{color}{content}{RESET}"

    return pattern.sub(replacer, text)


class JSONFormatter(json.JsonFormatter):
    """JSON formatter with optional inline color parsing."""

    def process_log_record(self, log_record):
        # If you want color-markup for local console readability,
        # but keep JSON fields clean, you can include both.
        raw_message = str(log_record.get("message", ""))
        log_record["message"] = colorize(raw_message)

        return super().process_log_record(log_record)


# Setup JSON handler (stdout is standard for Docker/Dokploy)
json_handler = logging.StreamHandler(sys.stdout)
json_handler.setFormatter(
    JSONFormatter(
        "{asctime}{levelname}{message}",
        style="{"
    )
)

# Main discord_bot logger
logger = logging.getLogger("discord_bot")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()
logger.addHandler(json_handler)
logger.propagate = False

# Discord library logger
discord_logger = logging.getLogger("discord")
discord_logger.handlers.clear()
discord_logger.addHandler(json_handler)
discord_logger.setLevel(logging.WARNING)
discord_logger.propagate = False