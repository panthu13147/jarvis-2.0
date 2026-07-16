import webview

def main():
    print("Starting Desktop App UI...")
    # Open UI natively using pywebview
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
