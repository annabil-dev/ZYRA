import sys
from app.application import Application

def main():
    try:
        app = Application(sys.argv)
        sys.exit(app.run())
    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR: Failed to start application: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
