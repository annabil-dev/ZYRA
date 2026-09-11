import platform
import psutil
from typing import Dict, Any

class HardwareDetector:
    """Detects system hardware and CUDA availability."""
    
    @staticmethod
    def get_hardware_info() -> Dict[str, Any]:
        """Gathers system hardware information without crashing if tools are missing."""
        info = {
            "os": platform.system() + " " + platform.release(),
            "cpu": platform.processor() or "Unknown CPU",
            "ram_total_gb": round(psutil.virtual_memory().total / (1024 ** 3), 2),
            "gpu": "Unknown GPU",
            "vram_gb": "Unknown",
            "cuda_available": False,
            "pytorch_version": "Not installed",
            "cuda_version": "N/A"
        }

        # Try detecting PyTorch and CUDA
        try:
            import torch
            info["pytorch_version"] = torch.__version__
            if torch.cuda.is_available():
                info["cuda_available"] = True
                info["cuda_version"] = torch.version.cuda
                info["gpu"] = torch.cuda.get_device_name(0)
                
                # Get total VRAM in GB
                try:
                    vram_bytes = torch.cuda.get_device_properties(0).total_memory
                    info["vram_gb"] = round(vram_bytes / (1024 ** 3), 2)
                except Exception:
                    pass
        except ImportError:
            pass
        except Exception:
            # Fallback to avoid crashing on unexpected errors (e.g. driver issues)
            pass

        if info["vram_gb"] == "Unknown":
            info["vram_gb"] = 0

        return info
