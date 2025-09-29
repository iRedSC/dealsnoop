import logging
import re

# ANSI color codes
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

class ColorFormatter(logging.Formatter):
    def format(self, record):
        record.msg = colorize(str(record.msg))  # apply colors to message content
        return super().format(record)
    
handler = logging.StreamHandler()
handler.setFormatter(ColorFormatter(
    "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))

logger = logging.getLogger("discord_bot")
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)