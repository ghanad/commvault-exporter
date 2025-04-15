import logging
import os
from logging.handlers import RotatingFileHandler
from .config_handler import ConfigHandler

def setup_logging(config: ConfigHandler) -> None:
    log_level = config.get("exporter", "log_level")
    logging_config = config.get("exporter", "logging", {})
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Create standard text formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s"
    )

    # Add console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Add file handler if configured
    log_file = logging_config.get("file")
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        max_size = logging_config.get("max_size", 10) * 1024 * 1024  # MB to bytes
        backup_count = logging_config.get("backup_count", 5)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_size,
            backupCount=backup_count
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Prevent duplicate logs if setup_logging is called multiple times
    if len(logger.handlers) > 2:  # Account for both console and file handlers
        logger.handlers = logger.handlers[-2:]  # Keep last two handlers