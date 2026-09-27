import os
import winreg

def clean_user_path():
    try:
        # Get User Path directly from Registry
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE)
        try:
            user_path, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            user_path = ""
            
        print(f"Original User Path length: {len(user_path)}")
        
        # Split and deduplicate, keeping order
        paths = [p.strip() for p in user_path.split(";") if p.strip()]
        seen = set()
        clean_paths = []
        
        for p in paths:
            p_lower = p.lower()
            if p_lower in seen:
                continue
            seen.add(p_lower)
            
            # Remove System paths that accidentally got copied here
            if p_lower.startswith(r"c:\windows") or p_lower.startswith(r"c:\program files"):
                continue
                
            clean_paths.append(p)
            
        # Ensure Python scripts are there
        import sysconfig
        scripts_1 = sysconfig.get_path('scripts')
        scripts_2 = sysconfig.get_path('scripts', f'{os.name}_user')
        
        for sp in [scripts_1, scripts_2]:
            if sp and sp.lower() not in seen:
                clean_paths.append(sp)
                
        new_path = ";".join(clean_paths)
        print(f"New User Path length: {len(new_path)}")
        
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
        winreg.CloseKey(key)
        
        # Notify Windows of environment change
        import ctypes
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        result = ctypes.c_long()
        ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", SMTO_ABORTIFHUNG, 5000, ctypes.byref(result))
        
        print("\n\033[92m[SUCCESS] Path has been deeply cleaned and fixed!\033[0m")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    clean_user_path()
