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


# Map log levels to colors
LEVEL_COLORS = {
    logging.DEBUG: COLORS["B"],   # Blue
    logging.INFO: COLORS["G"],    # Green
    logging.WARNING: COLORS["Y"], # Yellow
    logging.ERROR: COLORS["R"],   # Red
    logging.CRITICAL: COLORS["M"] # Magenta
}


class ColorFormatter(logging.Formatter):
    def format(self, record):
        # colorize the log level name
        level_color = LEVEL_COLORS.get(record.levelno, "")
        record.levelname = f"{level_color}{record.levelname}{RESET}"

        # colorize the message text if it uses $X$ markup
        record.msg = colorize(str(record.msg))

        return super().format(record)


# Setup handler and logger
handler = logging.StreamHandler()
handler.setFormatter(
    ColorFormatter(
        "%(levelname)-8s - %(message)s"
    )
)

logger = logging.getLogger("discord_bot")
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)
logger.propagate = False

# Remove default handlers from discord logger and attach our color handler
discord_logger = logging.getLogger("discord")
for h in discord_logger.handlers[:]:
    discord_logger.removeHandler(h)

discord_logger.addHandler(handler)
discord_logger.setLevel(logging.WARNING)
discord_logger.propagate = False