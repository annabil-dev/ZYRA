import os
import yaml
from typing import Dict, Any

class ConfigManager:
    """Manages the application configuration."""
    def __init__(self, config_path: str = "configs/default.yaml"):
        self.config_path = config_path
        self._config: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """Loads configuration from YAML file."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        with open(self.config_path, "r", encoding="utf-8") as file:
            try:
                self._config = yaml.safe_load(file) or {}
            except yaml.YAMLError as e:
                raise ValueError(f"Error parsing configuration file: {e}")

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Retrieves a configuration value using a dot-separated key path.
        Example: get('application.name')
        """
        keys = key_path.split('.')
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
