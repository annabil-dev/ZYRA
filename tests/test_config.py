import pytest
import yaml
from app.core.config import ConfigManager

def test_config_manager_load_success(tmp_path):
    # Create a temporary config file
    config_file = tmp_path / "test_config.yaml"
    config_data = {"application": {"name": "TestAI"}, "paths": {"datasets": "data"}}
    config_file.write_text(yaml.dump(config_data))

    manager = ConfigManager(config_path=str(config_file))
    assert manager.get("application.name") == "TestAI"
    assert manager.get("paths.datasets") == "data"
    assert manager.get("missing.key", "default_val") == "default_val"

def test_config_manager_file_not_found():
    with pytest.raises(FileNotFoundError):
        ConfigManager(config_path="nonexistent_config.yaml")
