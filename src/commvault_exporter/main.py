from .config_handler import ConfigHandler
from .collector import start_exporter
from .logger import setup_logging
import logging

logger = logging.getLogger(__name__)

import signal
import time

def run():
    # Initialize ConfigHandler with config file path
    config = ConfigHandler("config/config.yaml")
    logger.debug(f"Config type: {type(config)}, is ConfigHandler: {isinstance(config, ConfigHandler)}")
    setup_logging(config)
    start_exporter(config)
    
    # Keep process running until interrupted
    def handle_signal(signum, frame):
        logger.info("Received shutdown signal")
        raise SystemExit(0)
        
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    logger.info("Exporter running. Press Ctrl+C to stop.")
    while True:
        time.sleep(1)

if __name__ == '__main__':
    run()