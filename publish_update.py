import os
import sys
import zipfile
import json
import time
import shutil

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.join(root_dir, "app")
    publish_dir = os.path.join(root_dir, "publish")
    
    os.makedirs(publish_dir, exist_ok=True)
    
    zip_path = os.path.join(publish_dir, "update.zip")
    version_path = os.path.join(publish_dir, "version.json")
    
    print(f"Creating OTA update package from {app_dir}...")
    
    ai_dir = os.path.join(root_dir, "ai")
    
    # Create zip file
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for d in [app_dir, ai_dir]:
            for root, dirs, files in os.walk(d):
                for file in files:
                    if file.endswith('.pyc') or '__pycache__' in root:
                        continue
                    file_path = os.path.join(root, file)
                    # Keep the folder structure inside the zip
                    arcname = os.path.relpath(file_path, root_dir)
                    zipf.write(file_path, arcname)
    
    print(f"Created {zip_path}")
    
    # Create version info
    current_version = "v1.0.0"
    if os.path.exists(version_path):
        try:
            with open(version_path, 'r') as f:
                old_info = json.load(f)
                old_v = old_info.get("version", "v1.0.0")
                if isinstance(old_v, str) and old_v.count('.') == 2:
                    parts = old_v.replace('v', '').split('.')
                    current_version = f"v{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
                else:
                    current_version = "v1.0.0"
        except:
            current_version = "v1.0.0"
            
    version_info = {
        "version": current_version,
        "description": "Source code update"
    }
    
    with open(version_path, 'w') as f:
        json.dump(version_info, f, indent=4)
        
    print(f"Created version info: {version_info}")
    print("Update published successfully! Open ZYRA AI Desktop and click Check for Updates.")

if __name__ == "__main__":
    main()
