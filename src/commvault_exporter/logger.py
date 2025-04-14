import logging
from pythonjsonlogger import jsonlogger
from typing import Dict, Any
from .config_handler import ConfigHandler

class JsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["timestamp"] = record.created
        log_record["level"] = record.levelname
        log_record["module"] = record.module
        log_record["function"] = record.funcName
        log_record["line"] = record.lineno

def setup_logging(config: ConfigHandler) -> None:
    log_level = config.get("exporter", "log_level")
    logger = logging.getLogger()
    logger.setLevel(log_level)

    handler = logging.StreamHandler()
    formatter = JsonFormatter(
        "%(timestamp)s %(level)s %(module)s %(function)s %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Prevent duplicate logs if setup_logging is called multiple times
    if len(logger.handlers) > 1:
        logger.handlers = [handler]