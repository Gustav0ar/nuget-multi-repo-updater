import json
import yaml

class ConfigurationService:
    """Service for loading and managing configuration."""

    def __init__(self, config_file: str):
        self.config = self._load_config(config_file)

    def _load_config(self, config_file: str) -> dict:
        """Load configuration from a JSON or YAML file."""
        with open(config_file, 'r') as f:
            if config_file.endswith('.json'):
                return json.load(f)
            elif config_file.endswith(('.yaml', '.yml')):
                return yaml.safe_load(f)
            else:
                raise ValueError("Unsupported config file format. Use JSON or YAML.")

    def get(self, key: str, default=None):
        """Get a configuration value."""
        return self.config.get(key, default)
