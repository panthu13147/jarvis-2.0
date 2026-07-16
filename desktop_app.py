import threading
import time
import uvicorn
import webview
import keyboard
import requests
import sys
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None

def start_server():
    print("Starting Jarvis Backend Server...")
    # Run uvicorn programmatically
    uvicorn.run("jarvis.core.server:app", host="127.0.0.1", port=8000, log_level="warning")

def trigger_jarvis():
    try:
        requests.post("http://127.0.0.1:8000/api/trigger", timeout=2)
    except Exception:
        pass

def wake_word_listener():
    """Background listener using sounddevice to detect wake words.
    Currently uses an energy threshold as a mock for Porcupine wake word."""
    if sd is None:
        print("Sounddevice not installed. Wake word disabled.")
        return
        
    print("Listening for wake word (Mock)...")
    def audio_callback(indata, frames, time, status):
        volume_norm = np.linalg.norm(indata) * 10
        if volume_norm > 50:  # Arbitrary loud threshold
            print("Wake word detected!")
            trigger_jarvis()
            # Sleep briefly to avoid multiple triggers
            sd.sleep(3000)
            
    try:
        with sd.InputStream(callback=audio_callback):
            while True:
                time.sleep(1)
    except Exception as e:
        print(f"Wake word listener failed: {e}")

def main():
    # 1. Start FastAPI server in a daemon thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # 2. Start Wake-Word Engine in a daemon thread
    wake_thread = threading.Thread(target=wake_word_listener, daemon=True)
    wake_thread.start()

    # 3. Register Global Hotkey (Disabled)
    # keyboard.add_hotkey('ctrl+space', trigger_jarvis)
        print(f"Failed to register hotkey: {e}")

    # wait for server to bind
    time.sleep(2) 
    
    print("Starting Desktop App UI...")
    # 4. Open UI natively using pywebview
    window = webview.create_window(
        'JARVIS AI v2.0',
        'http://127.0.0.1:8000',
        width=400,
        height=600,
        frameless=False,
        easy_drag=True,
        on_top=True,
        text_select=True  # Enable text selection!
    )
    
    webview.start(private_mode=False)

if __name__ == "__main__":
    main()
