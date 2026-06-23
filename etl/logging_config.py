"""Centralized logging with color output. Import this in every ETL module."""

import logging
import colorlog


def get_logger(name: str) -> logging.Logger:
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s [%(levelname)s] %(name)s:%(reset)s %(message)s',
        datefmt='%H:%M:%S',
        log_colors={
            'DEBUG': 'cyan', 'INFO': 'green',
            'WARNING': 'yellow', 'ERROR': 'red', 'CRITICAL': 'bold_red'
        }
    ))

    # Also write to file
    file_handler = logging.FileHandler('etl_run.log')
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    ))

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.addHandler(file_handler)
    return logger
