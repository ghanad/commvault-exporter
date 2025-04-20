import os
import yaml
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class ConfigHandler:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = config_path
        self.config: Dict[str, Any] = self._load_defaults()
        self._load_config()
        self._apply_env_overrides()
        self._validate_config()

    def _load_defaults(self) -> Dict[str, Any]:
        return {
            "targets": {}, # Expects a dictionary of targets
            "exporter": {
                # Single port for the probe endpoint
                "port": 9658, # Default port for the /probe endpoint
                "log_level": "INFO",
                "timeout": 30,
                "logging": {
                    "file": None,
                    "max_size": 10,
                    "backup_count": 5
                }
            }
        }

    def _load_config(self) -> None:
        try:
            with open(self.config_path, 'r') as f:
                loaded_config = yaml.safe_load(f) or {}
                self._merge_configs(loaded_config)
            logger.info(f"Loaded configuration from {self.config_path}")
        except FileNotFoundError:
            logger.warning(f"Configuration file not found at {self.config_path}. Using defaults and environment variables.")
        except yaml.YAMLError as e:
            logger.error(f"Error parsing configuration file {self.config_path}: {e}")
            raise ValueError(f"Invalid YAML configuration: {e}") from e
        except Exception as e:
            logger.error(f"Failed to load configuration from {self.config_path}: {e}")
            raise

    def _merge_configs(self, new_config: Dict[str, Any]) -> None:
        # Merge 'exporter' section
        if "exporter" in new_config:
            if isinstance(new_config["exporter"], dict):
                # If 'probe_port' exists in the loaded config (old format), prefer it, but rename to 'port'
                if 'probe_port' in new_config['exporter']:
                    probe_port = new_config['exporter'].pop('probe_port')
                    if 'port' not in new_config['exporter']: # Only use probe_port if 'port' isn't explicitly set
                         new_config['exporter']['port'] = probe_port
                    else:
                         logger.warning("Ignoring legacy 'probe_port' in config, as 'port' is also defined.")
                self.config["exporter"].update(new_config["exporter"])
            else:
                logger.warning("Ignoring invalid 'exporter' section in config file (must be a dictionary).")

        # Replace 'targets' section entirely
        if "targets" in new_config:
            if isinstance(new_config["targets"], dict):
                self.config["targets"] = new_config["targets"]
            else:
                logger.warning("Ignoring invalid 'targets' section in config file (must be a dictionary).")

    def _apply_env_overrides(self) -> None:
        # Exporter settings overrides
        # Use EXPORTER_PORT for the single port setting
        if os.getenv("EXPORTER_PORT"):
             self.config["exporter"]["port"] = int(os.getenv("EXPORTER_PORT"))
        # Keep legacy EXPORTER_PROBE_PORT for backward compatibility, but warn if used alongside EXPORTER_PORT
        if os.getenv("EXPORTER_PROBE_PORT"):
            if os.getenv("EXPORTER_PORT"):
                logger.warning("Both EXPORTER_PORT and EXPORTER_PROBE_PORT are set. EXPORTER_PORT takes precedence.")
            else:
                logger.warning("EXPORTER_PROBE_PORT is deprecated, please use EXPORTER_PORT instead.")
                self.config["exporter"]["port"] = int(os.getenv("EXPORTER_PROBE_PORT"))

        if os.getenv("EXPORTER_LOG_LEVEL"):
             self.config["exporter"]["log_level"] = os.getenv("EXPORTER_LOG_LEVEL")
        if os.getenv("EXPORTER_TIMEOUT"):
             self.config["exporter"]["timeout"] = int(os.getenv("EXPORTER_TIMEOUT"))
        if os.getenv("EXPORTER_LOGGING_FILE"):
             self.config["exporter"]["logging"]["file"] = os.getenv("EXPORTER_LOGGING_FILE")

        # Note: Overriding specific target properties via env vars is complex and not implemented here.
        # Rely on the config file for target definitions.

    def _validate_config(self) -> None:
        """Performs basic validation of the loaded configuration."""
        if not isinstance(self.config.get("targets"), dict):
            raise ValueError("Configuration error: 'targets' must be a dictionary.")
        if not self.config["targets"]:
            logger.warning("No targets defined in configuration. Exporter will run but cannot probe anything.")

        required_target_keys = {"api_url", "username", "password"}
        for name, target_conf in self.config["targets"].items():
            if not isinstance(target_conf, dict):
                 raise ValueError(f"Configuration error: Target '{name}' must be a dictionary.")
            missing_keys = required_target_keys - target_conf.keys()
            if missing_keys:
                raise ValueError(f"Configuration error: Target '{name}' is missing required keys: {missing_keys}")

        if not isinstance(self.config.get("exporter"), dict):
            raise ValueError("Configuration error: 'exporter' section must be a dictionary.")
        if 'port' not in self.config['exporter']:
             raise ValueError("Configuration error: 'exporter' section must contain a 'port' key.")
        # Add more validation for exporter settings if needed (e.g., port ranges)


    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a config value from a specific section (mainly 'exporter')."""
        logger.debug(f"Config.get() called with section={section}, key={key}")
        if section not in self.config:
            logger.debug(f"Section '{section}' not found, returning default")
            return default

        section_data = self.config[section]
        if not isinstance(section_data, dict):
            logger.error(f"Section '{section}' is not a dict: {type(section_data)}")
            return default

        value = section_data.get(key, default)
        logger.debug(f"Config.get() returning: {value}")
        return value

    def get_target_config(self, target_name: str) -> Optional[Dict[str, Any]]:
        """Get the configuration dictionary for a specific target."""
        logger.debug(f"Looking up configuration for target: {target_name}")
        target_conf = self.config.get("targets", {}).get(target_name)
        if target_conf:
            # Inject global timeout into target config if not specified per-target
            if 'timeout' not in target_conf:
                target_conf['timeout'] = self.get('exporter', 'timeout', 30)
            # Inject global verify_ssl default if not specified per-target
            if 'verify_ssl' not in target_conf:
                 target_conf['verify_ssl'] = self.get('exporter', 'verify_ssl', True) # Default to True
            logger.debug(f"Found configuration for target '{target_name}': {target_conf}")
        else:
            logger.warning(f"Configuration for target '{target_name}' not found.")
        return target_conf

    def get_all_targets(self) -> Dict[str, Any]:
        """Get the entire targets dictionary."""
        return self.config.get("targets", {})

    def get_exporter_port(self) -> int:
        """Gets the single port the exporter should listen on."""
        return self.get('exporter', 'port', 9658) # Use default if somehow missing after validation