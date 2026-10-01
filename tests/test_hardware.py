import sys
from pathlib import Path

# These tests cover the archived desktop app, not the active ZYRA CLI package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "archives" / "legacy_app"))
from app.core.hardware import HardwareDetector

def test_hardware_detector():
    info = HardwareDetector.get_hardware_info()
    
    # Ensure all required keys exist and the method doesn't crash
    assert "os" in info
    assert "cpu" in info
    assert "ram_total_gb" in info
    assert "gpu" in info
    assert "vram_gb" in info
    assert "cuda_available" in info
    assert "pytorch_version" in info
    assert "cuda_version" in info
    
    # Type checking for ram
    assert isinstance(info["ram_total_gb"], (float, int))
