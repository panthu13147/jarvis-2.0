import threading
import time
import uvicorn
import keyboard
import requests
import subprocess
import os
import sys
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None

def start_server():
    print("Starting Jarvis Backend Server...")
    uvicorn.run("jarvis.core.server:app", host="127.0.0.1", port=8000, log_level="warning")

def launch_ui():
    """Launches the pywebview UI in a separate process so it can be closed without killing the service."""
    try:
        resp = requests.post("http://127.0.0.1:8000/api/trigger", timeout=2)
        data = resp.json()
        if data.get("active_clients", 0) == 0:
            print("No active UI clients. Launching UI process...")
            subprocess.Popen([sys.executable, "ui_client.py"])
    except Exception as e:
        print(f"Error triggering JARVIS: {e}")
        subprocess.Popen([sys.executable, "ui_client.py"])

def wake_word_listener():
    if sd is None:
        print("Sounddevice not installed. Wake word disabled.")
        return
        
    print("Listening for wake word (Mock)...")
    def audio_callback(indata, frames, time, status):
        volume_norm = np.linalg.norm(indata) * 10
        if volume_norm > 50: 
            print("Wake word detected!")
            launch_ui()
            sd.sleep(3000)
            
    try:
        with sd.InputStream(callback=audio_callback):
            while True:
                time.sleep(1)
    except Exception as e:
        print(f"Wake word listener failed: {e}")

def main():
    # 1. Start FastAPI server
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # 2. Start Wake-Word Engine
    wake_thread = threading.Thread(target=wake_word_listener, daemon=True)
    wake_thread.start()

    # 3. Register Global Hotkey (Disabled)
    # keyboard.add_hotkey('ctrl+space', launch_ui)

    # wait for server to bind
    time.sleep(2) 
    
    # 4. Launch UI for the first time
    launch_ui()

    print("JARVIS Background OS Service is running. Press Ctrl+C to exit.")
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down JARVIS service.")

if __name__ == "__main__":
    main()
