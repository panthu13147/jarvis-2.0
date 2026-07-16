
import requests
import os
from dotenv import load_dotenv

load_dotenv()
GROQ_KEY = os.environ.get("GROQ_API_KEY")

def test_stt():
    with open("empty.webm", "wb") as f:
        # Dummy webm header
        f.write(b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\xf7\x81\x01\x42\xf2\x81\x04\x42\xf3\x81\x08\x42\x82\x84\x77\x65\x62\x6d\x42\x87\x81\x02\x42\x85\x81\x02\x18\x53\x80\x67\x01\xff\xff\xff\xff\xff\xff\xff")
    
    with open("empty.webm", "rb") as f:
        resp = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            files={"file": ("empty.webm", f, "audio/webm")},
            data={"model": "whisper-large-v3", "language": "en"}
        )
        print("Status:", resp.status_code)
        print("Text:", resp.text)

if __name__ == "__main__":
    test_stt()

