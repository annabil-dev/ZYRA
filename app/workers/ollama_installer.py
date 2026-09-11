import os
import subprocess
import urllib.request
import time
from PySide6.QtCore import QThread, Signal

class OllamaInstallerWorker(QThread):
    progress_update = Signal(int, str)
    finished = Signal(bool, str)

    def run(self):
        installer_url = "https://ollama.com/download/OllamaSetup.exe"
        installer_path = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "OllamaSetup.exe")
        
        try:
            self.progress_update.emit(10, "Downloading OllamaSetup.exe... (This may take a few minutes)")
            
            # Simple download with urllib
            def report(count, block_size, total_size):
                if total_size > 0:
                    percent = int(count * block_size * 100 / total_size)
                    # Scale to 10% - 60%
                    scaled = 10 + int(percent * 0.5)
                    self.progress_update.emit(scaled, f"Downloading OllamaSetup.exe... {percent}%")
                    
            urllib.request.urlretrieve(installer_url, installer_path, reporthook=report)
            
            self.progress_update.emit(65, "Download complete. Waiting for Windows UAC permission...")
            
            # Run the installer silently
            # Note: /silent flag works for InnoSetup and many modern installers, 
            # OllamaSetup is an InnoSetup or similar, but /silent might still trigger UAC.
            process = subprocess.run([installer_path, "/SILENT"], capture_output=True, text=True)
            
            if process.returncode != 0:
                self.finished.emit(False, f"Installer failed with code {process.returncode}: {process.stderr}")
                return
                
            self.progress_update.emit(90, "Installation complete. Starting Ollama Engine...")
            
            # Wait for Ollama to boot up (localhost:11434)
            retries = 15
            import requests
            for _ in range(retries):
                try:
                    r = requests.get("http://localhost:11434/")
                    if r.status_code == 200:
                        self.progress_update.emit(100, "Ollama is ready!")
                        self.finished.emit(True, "Success")
                        return
                except:
                    time.sleep(2)
                    
            self.finished.emit(False, "Ollama installed but could not connect to localhost:11434.")
            
        except Exception as e:
            self.finished.emit(False, str(e))
        finally:
            if os.path.exists(installer_path):
                try:
                    os.remove(installer_path)
                except:
                    pass
