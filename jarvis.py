import threading
import time
import uvicorn
import pystray
import keyboard
import webbrowser
from PIL import Image, ImageDraw
import sys

def create_icon_image():
    # Generate a simple blue glowing orb image for the tray icon
    img = Image.new('RGB', (64, 64), color=(0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), fill=(0, 150, 255), outline=(0, 255, 255))
    return img

def start_server():
    print("Starting Jarvis Backend Server...")
    # Run uvicorn programmatically
    uvicorn.run("server:app", host="127.0.0.1", port=8000, log_level="warning")

def open_ui():
    webbrowser.open("http://127.0.0.1:8000")

def on_quit(icon, item):
    icon.stop()
    sys.exit(0)

def trigger_jarvis():
    # When global hotkey is pressed, open or focus the UI
    open_ui()

def main():
    # 1. Start FastAPI server in a daemon thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # 2. Register Global Hotkey (Ctrl + Space)
    print("Registering global hotkey: Ctrl + Space")
    try:
        keyboard.add_hotkey('ctrl+space', trigger_jarvis)
    except Exception as e:
        print(f"Failed to register hotkey: {e}")

    # 3. Create System Tray Icon
    print("Jarvis is now running in the background (System Tray).")
    icon_image = create_icon_image()
    menu = pystray.Menu(
        pystray.MenuItem("Open Interface", lambda icon, item: open_ui()),
        pystray.MenuItem("Quit", on_quit)
    )
    
    icon = pystray.Icon("Jarvis", icon_image, "Jarvis AI", menu)
    
    # 4. Open UI automatically on boot
    time.sleep(1) # wait for server to bind
    open_ui()
    
    # Run the tray icon (blocking call)
    icon.run()

if __name__ == "__main__":
    main()
