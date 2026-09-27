import os
import sys
import subprocess
import shutil
from pathlib import Path

def main():
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass
            
    print("\n\033[96m🚀 ZYRA PyPI Auto-Publisher\033[0m")
    print("-" * 35)

    # 1. Membersihkan folder dist lama
    print("\n\033[93m[1/4] Membersihkan folder dist...\033[0m")
    if os.path.exists("dist"):
        shutil.rmtree("dist")
        print("✅ Folder dist bersih.")
    else:
        print("✅ Tidak ada folder dist.")
        
    # 2. Build first so a broken release never gets pushed.
    print("\n\033[93m[2/4] Mem-build package...\033[0m")
    result = subprocess.run([sys.executable, "-m", "build"], capture_output=False)
    if result.returncode != 0:
        print("\033[91m❌ Build gagal! Source belum dipush atau diupload.\033[0m")
        return

    # 3. Push only release inputs. Never stage build outputs, local env, archives, or secrets.
    print("\n\033[93m[3/4] Nge-push source release ke GitHub...\033[0m")
    try:
        release_paths = ["README.md", "pyproject.toml", "requirements.txt", "publish.py", "ai", "p2p",
                         "zyra_cmd", "tests", "zyra_network.egg-info"]
        subprocess.run(["git", "add", "-A", "--", *release_paths], check=True)
        # Parse version from pyproject.toml
        version = "update"
        with open("pyproject.toml", "r") as f:
            for line in f:
                if line.startswith("version ="):
                    version = line.split('"')[1]
                    break
        staged = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if staged.returncode == 0:
            print("❌ Tidak ada perubahan release yang di-stage; batal agar tidak membuat publish kosong.")
            return
        subprocess.run(["git", "commit", "-m", f"Auto-publish v{version}"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print(f"✅ Berhasil push ke GitHub dengan pesan: Auto-publish v{version}")
    except subprocess.CalledProcessError as e:
        print(f"\033[91m❌ Gagal push ke GitHub: {e}\033[0m")
        return

    
    # 4. Mengecek kredensial PyPI di konfigurasi komputer (.pypirc)
    pypirc_path = Path.home() / ".pypirc"
    if not pypirc_path.exists():
        print("\n\033[91m[!] Kredensial PyPI belum disetting.\033[0m")
        print("Ini hanya perlu dilakukan SATU KALI.")
        token = input("Masukkan API Token PyPI milikmu (biasanya berawalan pypi-): ").strip()
        if token:
            pypirc_content = f"""[pypi]
username = __token__
password = {token}
"""
            with open(pypirc_path, "w") as f:
                f.write(pypirc_content)
            print("\033[92m✅ Kredensial berhasil disimpan di ~/.pypirc\033[0m")
        else:
            print("\033[91m❌ Upload dibatalkan: Token kosong.\033[0m")
            return

    # 5. Upload ke PyPI via Twine
    print("\n\033[93m[4/4] Meng-upload ke PyPI...\033[0m")
    
    # Kumpulkan semua file di folder dist/
    dist_files = [os.path.join("dist", f) for f in os.listdir("dist")]
    
    twine_cmd = [sys.executable, "-m", "twine", "upload", "--skip-existing"] + dist_files
    result = subprocess.run(twine_cmd, capture_output=False)
    
    if result.returncode == 0:
        print("\n\033[92m🎉 BAM! ZYRA berhasil dipublish ke PyPI!\033[0m")
    else:
        print("\n\033[91m❌ Upload gagal!\033[0m")

if __name__ == "__main__":
    main()
