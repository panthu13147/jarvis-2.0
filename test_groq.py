import os
import requests
import json
from pathlib import Path

GROQ_KEY = None
candidates = [
    Path("C:/Users/panth/Desktop/jarvis v1.0/api keys/groq api key.txt"),
    Path("C:/Users/panth/Desktop/jarvis_ai v2.0/api keys/groq api key.txt")
]
for path in candidates:
    if path.exists():
        GROQ_KEY = path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        break

import sys
from pathlib import Path
sys.path.append(str(Path("C:/Users/panth/Desktop/jarvis_ai v2.0")))
from jarvis.core import tools

req_payload = {
    "model": "llama-3.3-70b-versatile",
    "messages": [{"role": "user", "content": "Say hello world."}],
    "temperature": 0.7,
    "stream": True,
    "tools": tools.GROQ_TOOLS,
    "tool_choice": "auto"
}

resp = requests.post(
    "https://api.groq.com/openai/v1/chat/completions",
    headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
    json=req_payload,
    stream=True,
    timeout=15
)
resp.raise_for_status()

for line in resp.iter_lines():
    print("LINE:", line)
