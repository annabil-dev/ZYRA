import os
from app.core.config import ConfigManager

class PathManager:
    """Manages paths for the application and ensures they exist."""
    def __init__(self, config: ConfigManager, base_dir: str = "."):
        self.config = config
        self.base_dir = os.path.abspath(base_dir)
        self.paths = {}
        self._initialize_paths()

    def _initialize_paths(self) -> None:
        """Initializes and creates necessary directories."""
        path_configs = self.config.get("paths", {})
        
        for key, relative_path in path_configs.items():
            full_path = os.path.join(self.base_dir, relative_path)
            self.paths[key] = full_path
            
            # Ensure directory exists
            os.makedirs(full_path, exist_ok=True)

    def get_path(self, key: str) -> str:
        """Retrieves a specific path by key."""
        if key not in self.paths:
            raise KeyError(f"Path key '{key}' not found in configuration.")
        return self.paths[key]
