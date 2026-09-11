import pytest
import os
from app.core.paths import PathManager

class DummyConfig:
    def get(self, key, default=None):
        if key == "paths":
            return {"test_dir": "test_folder"}
        return default

def test_path_manager_creates_directories(tmp_path):
    config = DummyConfig()
    manager = PathManager(config, base_dir=str(tmp_path))
    
    expected_path = os.path.join(str(tmp_path), "test_folder")
    assert manager.get_path("test_dir") == expected_path
    assert os.path.isdir(expected_path)

def test_path_manager_key_error():
    config = DummyConfig()
    manager = PathManager(config, base_dir=".")
    with pytest.raises(KeyError):
        manager.get_path("non_existent_key")
