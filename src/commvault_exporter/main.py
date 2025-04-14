from .config_handler import ConfigHandler
from .collector import start_exporter
from .logger import setup_logging

def run():
    config = ConfigHandler()
    setup_logging(config)
    start_exporter(config)

if __name__ == '__main__':
    run()