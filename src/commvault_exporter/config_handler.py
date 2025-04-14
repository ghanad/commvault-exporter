import os
import yaml
from typing import Dict, Any

class ConfigHandler:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = config_path
        self.config: Dict[str, Any] = self._load_defaults()
        self._load_config()
        self._apply_env_overrides()

    def _load_defaults(self) -> Dict[str, Any]:
        return {
            "commvault": {
                "api_url": "",
                "username": "",
                "password": "",
                "auth_token": ""
            },
            "exporter": {
                "port": 9657,
                "log_level": "INFO",
                "timeout": 30
            }
        }

    def _load_config(self) -> None:
        try:
            with open(self.config_path, 'r') as f:
                loaded_config = yaml.safe_load(f) or {}
                self._merge_configs(loaded_config)
        except FileNotFoundError:
            pass

    def _merge_configs(self, new_config: Dict[str, Any]) -> None:
        for section, values in new_config.items():
            if section in self.config:
                self.config[section].update(values)
            else:
                self.config[section] = values

    def _apply_env_overrides(self) -> None:
        # Commvault settings
        if os.getenv("COMMVAULT_API_URL"):
            self.config["commvault"]["api_url"] = os.getenv("COMMVAULT_API_URL")
        if os.getenv("COMMVAULT_USERNAME"):
            self.config["commvault"]["username"] = os.getenv("COMMVAULT_USERNAME")
        if os.getenv("COMMVAULT_PASSWORD"):
            self.config["commvault"]["password"] = os.getenv("COMMVAULT_PASSWORD")
        
        # Exporter settings
        if os.getenv("EXPORTER_PORT"):
            self.config["exporter"]["port"] = int(os.getenv("EXPORTER_PORT"))
        if os.getenv("EXPORTER_LOG_LEVEL"):
            self.config["exporter"]["log_level"] = os.getenv("EXPORTER_LOG_LEVEL")
        if os.getenv("EXPORTER_TIMEOUT"):
            self.config["exporter"]["timeout"] = int(os.getenv("EXPORTER_TIMEOUT"))

    def get(self, *keys) -> Any:
        result = self.config
        for key in keys:
            result = result.get(key, {})
        return result