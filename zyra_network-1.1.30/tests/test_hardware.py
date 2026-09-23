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
