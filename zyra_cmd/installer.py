import os
import sys
import time
import subprocess
import urllib.request
import json

def is_ollama_running():
    try:
        req = urllib.request.urlopen("http://localhost:11434/", timeout=2)
        return req.getcode() == 200
    except:
        return False

def check_and_install_ollama():
    if is_ollama_running():
        return True
        
    # Check if ollama is in PATH
    has_ollama = False
    try:
        res = subprocess.run(["ollama", "--version"], capture_output=True, text=True)
        if res.returncode == 0:
            has_ollama = True
    except:
        pass
        
    if has_ollama:
        print("\033[93m[System]\033[0m Ollama is installed but not running. Trying to start it...")
        # On Windows, we can use subprocess.Popen to start it in background
        if os.name == 'nt':
            subprocess.Popen(["ollama", "serve"], creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        for _ in range(10):
            time.sleep(1)
            if is_ollama_running():
                print("\033[92m[System]\033[0m Ollama started successfully.")
                return True
        print("\033[91m[Error]\033[0m Failed to start Ollama. Please start it manually.")
        return False
        
    # Ask to install
    print("\n\033[91m[System]\033[0m Ollama AI Engine is not installed on this system.")
    print("Ollama is required as the local engine for ZYRA CLI.")
    ans = input("\033[96mDo you want ZYRA to automatically download and install Ollama? (Y/n): \033[0m").strip().lower()
    if ans == 'n':
        print("\033[93mInstallation skipped. ZYRA will run in Client-Only mode.\033[0m")
        return False
        
    if sys.platform.startswith("linux"):
        print("\n\033[94m[System]\033[0m Installing Ollama for Linux (may require sudo password)...")
        try:
            process = subprocess.run("curl -fsSL https://ollama.com/install.sh | sh", shell=True)
            if process.returncode != 0:
                print(f"\033[91m[Error]\033[0m Linux installer failed with code {process.returncode}")
                return False
        except Exception as e:
            print(f"\033[91m[Error]\033[0m Failed to run Linux installer: {e}")
            return False
            
    elif sys.platform == "darwin":
        print("\n\033[91m[System]\033[0m Auto-install is not supported on macOS yet. Please install manually from https://ollama.com/download")
        return False
        
    else:
        # Windows Logic
        installer_url = "https://ollama.com/download/OllamaSetup.exe"
        installer_path = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "OllamaSetup.exe")
        
        print("\n\033[94m[System]\033[0m Downloading OllamaSetup.exe (this may take a few minutes)...")
        try:
            def report(count, block_size, total_size):
                if total_size > 0:
                    percent = int(count * block_size * 100 / total_size)
                    sys.stdout.write(f"\r\033[96mDownloading... {percent}%\033[0m")
                    sys.stdout.flush()
            urllib.request.urlretrieve(installer_url, installer_path, reporthook=report)
            print("\n\033[92m[System]\033[0m Download complete!")
        except Exception as e:
            print(f"\n\033[91m[Error]\033[0m Failed to download: {e}")
            return False
            
        print("\033[94m[System]\033[0m Installing Ollama (Please allow UAC prompt if it appears)...")
        try:
            process = subprocess.run([installer_path, "/SILENT"], capture_output=True, text=True)
            if process.returncode != 0:
                print(f"\033[91m[Error]\033[0m Installer failed with code {process.returncode}")
                return False
        except Exception as e:
            print(f"\033[91m[Error]\033[0m Failed to run installer: {e}")
            return False
        
    print("\033[94m[System]\033[0m Waiting for Ollama engine to start...")
    for _ in range(15):
        if is_ollama_running():
            print("\033[92m[System]\033[0m Ollama is ready!")
            return True
        time.sleep(2)
        
    print("\033[91m[Error]\033[0m Ollama installed but could not connect to localhost:11434.")
    return False

def check_and_pull_model(default_model):
    try:
        req = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        data = json.loads(req.read().decode('utf-8'))
        models = [m['name'] for m in data.get('models', [])]
        
        if models:
            # Exact match or matched tag
            if any(m == default_model or m.startswith(default_model + ':') for m in models):
                return default_model
            # If default is not installed but others are, just use the first available one!
            return models[0]
            
    except Exception as e:
        print(f"\033[91m[Error]\033[0m Failed to fetch models: {e}")
        return default_model # Fallback to trying to start anyway
        
    # Model not found, show interactive menu
    print(f"\n\033[93m[System]\033[0m You don't have any recommended AI models installed.")
    print("\033[1mPlease select an AI model to download (choose based on your laptop specs):\033[0m")
    print("  1. \033[96mllama3.2:1b\033[0m  - [Very Light] Needs ~2GB RAM")
    print("  2. \033[96mllama3.2:3b\033[0m  - [Balanced]   Needs ~4GB RAM")
    print("  3. \033[96mqwen2.5:7b\033[0m   - [Smartest]   Needs ~8GB RAM (Best for Coding)")
    print("  4. \033[96mllama3.1:8b\033[0m  - [Heavy]      Needs ~8GB+ RAM")
    
    choices = {
        '1': 'llama3.2:1b',
        '2': 'llama3.2:3b',
        '3': 'qwen2.5:7b',
        '4': 'llama3.1:8b'
    }
    
    selected_model = None
    while True:
        ans = input("\033[93mEnter number (1-4): \033[0m").strip()
        if ans in choices:
            selected_model = choices[ans]
            break
        print("\033[91mInvalid choice. Please enter a number between 1 and 4.\033[0m")
        
    print(f"\n\033[94m[System]\033[0m Downloading {selected_model}... (This will take a while depending on your internet speed)")
    
    # Run ollama pull directly
    try:
        process = subprocess.run(["ollama", "pull", selected_model])
        
        if process.returncode == 0:
            print(f"\n\033[92m[System]\033[0m {selected_model} successfully downloaded!")
            return selected_model
        else:
            print(f"\n\033[91m[Error]\033[0m Failed to pull model.")
            return selected_model # Return anyway so the REPL can try to catch the error
    except Exception as e:
        print(f"\n\033[91m[Error]\033[0m Failed to execute ollama pull: {e}")
        return selected_model
