import os
import sys
import subprocess

def main():
    print("Mencari lokasi script Python kamu...")
    import sysconfig
    
    scripts_dir_1 = sysconfig.get_path('scripts')
    scripts_dir_2 = sysconfig.get_path('scripts', f'{os.name}_user')
    
    print(f"Menambahkan folder 1: {scripts_dir_1}")
    print(f"Menambahkan folder 2: {scripts_dir_2}")
    
    try:
        cmd = f'$userPath = [Environment]::GetEnvironmentVariable("Path", "User"); [Environment]::SetEnvironmentVariable("Path", $userPath + ";{scripts_dir_1};{scripts_dir_2}", "User")'
        subprocess.run(["powershell", "-Command", cmd], check=True)
        print("\n\033[92m[SUCCESS] Berhasil ditambahkan ke PATH Windows!\033[0m")
        print("TUTUP terminal ini dan BUKA terminal baru, lalu ketik: zyra")
    except Exception as e:
        print(f"\n\033[91m[ERROR] Gagal menambahkan ke PATH: {e}\033[0m")

if __name__ == "__main__":
    main()
