import sys
import os

# Base directory for the bundled app
base_dir = os.path.dirname(os.path.abspath(__file__))

# OTA Update Injection
# If we are compiled (frozen), check if there is an 'updates' folder in APPDATA
if getattr(sys, 'frozen', False):
    user_data_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ZYRA AI")
    update_dir = os.path.join(user_data_dir, "updates")
    if os.path.exists(update_dir):
        # Insert at the very beginning of sys.path to override bundled modules
        sys.path.insert(0, update_dir)

sys.path.append(base_dir)

from app.main import main

if __name__ == "__main__":
    main()
