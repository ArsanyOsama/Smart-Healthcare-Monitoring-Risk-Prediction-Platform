"""Centralized logging. Emoji-safe for Windows."""

import logging
import colorlog
import sys


class EmojiSafeFormatter(colorlog.ColoredFormatter):
    """Intercepts log messages and replaces emojis with safe ASCII text."""

    def format(self, record):
        if isinstance(record.msg, str):
            record.msg = (record.msg
                          .replace('🏥', '[SYSTEM]')
                          .replace('✅', '[OK]')
                          .replace('❌', '[FAIL]')
                          .replace('⚠️', '[WARN]')
                          .replace('🎉', '[SUCCESS]')
                          .replace('ℹ️', '[INFO]')
                          .replace('—', '-'))
        return super().format(record)


def get_logger(name: str) -> logging.Logger:
    handler = colorlog.StreamHandler(sys.stdout)

    # Use our custom EmojiSafeFormatter
    handler.setFormatter(EmojiSafeFormatter(
        '%(log_color)s%(asctime)s [%(levelname)s] %(name)s:%(reset)s %(message)s',
        datefmt='%H:%M:%S',
        log_colors={
            'DEBUG': 'cyan', 'INFO': 'green',
            'WARNING': 'yellow', 'ERROR': 'red', 'CRITICAL': 'bold_red'
        }
    ))

    # Safe file handler
    file_handler = logging.FileHandler('etl_run.log', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    ))

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        logger.addHandler(handler)
        logger.addHandler(file_handler)

    return logger
