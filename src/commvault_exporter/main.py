from .config_handler import ConfigHandler
# Import the correct, renamed starting function
from .collector.collector import start_exporter
from .logger import setup_logging
import logging
import signal
import sys # Use sys.exit

logger = logging.getLogger(__name__)

# Keep track if shutdown is initiated
_shutdown_initiated = False

def handle_signal(signum, frame):
    """Handles termination signals gracefully."""
    global _shutdown_initiated
    if not _shutdown_initiated:
        _shutdown_initiated = True
        logger.info(f"Received signal {signum}. Initiating shutdown...")
        # The server running via serve_forever() needs to be shut down.
        # This signal handler will interrupt serve_forever(),
        # allowing the try...except block in start_http_server to handle cleanup.
        # We can exit here, or let the server shutdown() complete.
        # The KeyboardInterrupt exception handler in start_http_server now handles shutdown.
        # Raising SystemExit here is still a valid way to stop.
        sys.exit(0) # Or just return and let the exception handler do the work
    else:
        logger.warning("Shutdown already in progress.")


def run():
    # Setup signal handlers early
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    config = None # Initialize config to None
    try:
        # Initialize ConfigHandler
        config = ConfigHandler("config/config.yaml")

        # Setup logging using the loaded config
        setup_logging(config)

        logger.info("Configuration loaded and logging initialized.")
        logger.debug(f"Config type: {type(config)}, is ConfigHandler: {isinstance(config, ConfigHandler)}")

        # Start the exporter's single HTTP server
        # This function will block until the server is stopped (e.g., by signal)
        start_exporter(config)

        logger.info("Exporter server has stopped.") # Reached after serve_forever completes

    except ValueError as e:
         # Log configuration errors specifically
         print(f"ERROR: Configuration validation failed: {e}", file=sys.stderr)
         logging.critical(f"Configuration validation failed: {e}", exc_info=False) # Use critical level
         sys.exit(1) # Exit with error code
    except SystemExit as e:
        # Allow sys.exit calls (like from signal handler or port conflict) to propagate
        logger.info(f"Exiting with status code {e.code}")
        sys.exit(e.code)
    except Exception as e:
        # Catch any other unexpected errors during startup or runtime
        logger.critical("An unexpected critical error occurred:", exc_info=True)
        sys.exit(1) # Exit with error code

if __name__ == '__main__':
    run()