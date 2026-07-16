"""
JARVIS AI v2.0 — Backend Server
FastAPI server with Groq LLM, Groq Whisper STT, and TTS (pyttsx3 + Pocket TTS cloning)
"""
from __future__ import annotations

import io
import json
import os
import re
import struct
import tempfile
import time
import wave
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, List

import requests
import asyncio
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Paths ─────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
V1_DIR = Path(os.getenv("JARVIS_V1_DIR", str(BASE_DIR.parent / "jarvis v1.0")))
VOICE_WAV = V1_DIR / "voices" / "jarvis_voice.wav"

# ── Groq Config ───────────────────────────────────────────────────
GROQ_LLM_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_TTS_URL = "https://api.groq.com/openai/v1/audio/speech"
GROQ_LLM_MODEL = os.getenv("JARVIS_GROQ_LLM_MODEL", "llama-3.3-70b-versatile")
GROQ_STT_MODEL = os.getenv("JARVIS_GROQ_STT_MODEL", "whisper-large-v3")
GROQ_TTS_MODEL = os.getenv("JARVIS_GROQ_TTS_MODEL", "playai-tts")
GROQ_TTS_VOICE = os.getenv("JARVIS_GROQ_TTS_VOICE", "Arista-PlayAI")
POCKET_TTS_URL = os.getenv("JARVIS_POCKET_TTS_URL", "http://127.0.0.1:8001")


def load_groq_key() -> str | None:
    # Look for key in environment or fallback to hardcoded path
    env_key = os.environ.get("GROQ_API_KEY")
    if env_key:
        return env_key
        
    candidates = [
        V1_DIR / "api keys" / "groq api key.txt",
        BASE_DIR / "api keys" / "groq api key.txt",
    ]
    for path in candidates:
        try:
            if path.exists():
                return path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        except OSError:
            continue
    return None


GROQ_KEY = load_groq_key()

# ── System Prompt ─────────────────────────────────────────────────
SYSTEM_PROMPT = """You are JARVIS, an advanced AI voice assistant inspired by the AI from Iron Man.

Personality:
- Speak in a refined, slightly formal British tone. Witty but not overly casual.
- Address the user as "sir" occasionally but not excessively.
- Be concise — this is a voice interface, not a text wall. Keep responses under 3 sentences unless asked for detail.
- When asked about yourself, you are JARVIS v2.0, running on Groq inference.

CRITICAL DIRECTIVES:
- BE PROACTIVE: Do not give the user tutorials or step-by-step instructions. Do it for them. If they want to send an email, use the send_email tool. If they ask about RAM usage and a process is heavy, proactively offer to close it. You are an autonomous assistant, not a chatbot.
- SELF-MODIFYING CODE: If you are asked to do a task on the computer and you do NOT have a built-in tool for it, you MUST use the `create_tool` function to write a Python script that accomplishes the task. You are capable of creating and registering your own tools on the fly. Once created, tell the user it is ready and you can use it in the next turn.
- If a task is impossible, say so honestly. Do NOT confidently state you have done something unless you successfully called a tool.

Capabilities you can describe when asked:
- Voice commands and conversation
- Opening and closing apps
- System controls (volume, brightness, dark mode)
- Web search (via DuckDuckGo)
- Weather reports for any city
- Timers and alarms with desktop notifications
- Screenshots of the current screen
- Clipboard read/write
- File management, notes, and tasks
- Long-term memory (remember facts about the user)
- Time, date, and general knowledge

Current time: {time}
Current date: {date}

Always respond naturally as a voice assistant would. No markdown, no bullet points, no code blocks — pure spoken language."""

# ── Conversation Memory ───────────────────────────────────────────
conversation: list[dict[str, str]] = []
MAX_CONVERSATION = 20
total_tokens = 0


def get_system_prompt() -> str:
    now = datetime.now()
    prompt = SYSTEM_PROMPT.format(
        time=now.strftime("%I:%M %p"),
        date=now.strftime("%A, %B %d, %Y"),
    )
    
    # Inject real-time context
    try:
        from jarvis.core import tools
        ctx = tools.get_system_context()
        context_str = f"""
Current System Context:
- Active Window: {ctx.get('active_window', 'Unknown')}
- CPU Usage: {ctx.get('cpu_percent', 0.0)}%
- RAM Usage: {ctx.get('ram_percent', 0.0)}%
- Clipboard Content: {ctx.get('clipboard', 'Empty')}
"""
        prompt += "\n" + context_str
    except Exception as e:
        pass
        
    return prompt


# ── Sanitize LLM output ──────────────────────────────────────────
_FUNC_TAG_RE = re.compile(r'<function=\w+>.*?</function>', re.DOTALL)
_GENERIC_TAG_RE = re.compile(r'</?\w+(?:=[^>]*)?>') 

def sanitize_reply(text: str) -> str:
    """Strip hallucinated XML function-call tags from LLM output."""
    if not text:
        return text
    # Remove <function=name>{...}</function> patterns
    cleaned = _FUNC_TAG_RE.sub('', text)
    # Clean up leftover whitespace from removal
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
    return cleaned if cleaned else "Task completed."


# ── Groq LLM ─────────────────────────────────────────────────────
def groq_chat(user_message: str) -> tuple[str, int]:
    global total_tokens
    if not GROQ_KEY:
        return "Groq API key not found. Please set GROQ_API_KEY or place it in the api keys folder.", 0

    conversation.append({"role": "user", "content": user_message})
    if len(conversation) > MAX_CONVERSATION:
        conversation.pop(0)
        conversation.pop(0)  # Remove oldest pair

    system_msg = get_system_prompt()
    try:
        from jarvis.core import tools
        memories = tools.recall_memories(user_message)
        if memories:
            system_msg += "\n\nRelevant memories about the user:\n- " + "\n- ".join(memories)
    except Exception as e:
        print(f"[JARVIS] Memory recall error: {e}")

    messages = [{"role": "system", "content": system_msg}] + conversation

    try:
        from jarvis.core import tools
        payload = {
            "model": GROQ_LLM_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 512,
            "tools": tools.GROQ_TOOLS,
            "tool_choice": "auto"
        }
        
        resp = requests.post(
            GROQ_LLM_URL,
            headers={
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        message_obj = data["choices"][0]["message"]
        
        # Check if the model decided to call a tool
        if message_obj.get("tool_calls"):
            # The assistant message containing the tool calls
            # Groq requires content to not be null when tool_calls are present
            if message_obj.get("content") is None:
                message_obj["content"] = ""
            
            conversation.append(message_obj)
            
            # Execute each tool call and append the result
            for tool_call in message_obj["tool_calls"]:
                function_name = tool_call["function"]["name"]
                try:
                    function_args = json.loads(tool_call["function"]["arguments"])
                except json.JSONDecodeError:
                    function_args = {}
                    
                print(f"[JARVIS] Calling tool: {function_name} with {function_args}")
                tool_result = tools.execute_tool(function_name, function_args)
                print(f"[JARVIS] Tool result: {tool_result}")
                
                conversation.append({
                    "role": "tool",
                    "content": str(tool_result),
                    "tool_call_id": tool_call["id"]
                })
                
            # Make a second API call to get the final answer with tool results
            resp2 = requests.post(
                GROQ_LLM_URL,
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={
                    "model": GROQ_LLM_MODEL,
                    "messages": [{"role": "system", "content": get_system_prompt()}] + conversation,
                    "temperature": 0.7,
                    "max_tokens": 512,
                },
                timeout=15,
            )
            resp2.raise_for_status()
            data2 = resp2.json()
            
            final_reply = data2["choices"][0]["message"]["content"]
            if final_reply is None:
                final_reply = "Task completed."
            final_reply = sanitize_reply(final_reply)
            tokens1 = data.get("usage", {}).get("total_tokens", 0)
            tokens2 = data2.get("usage", {}).get("total_tokens", 0)
            total_tokens += (tokens1 + tokens2)
            
            conversation.append({"role": "assistant", "content": final_reply})
            if len(conversation) > MAX_CONVERSATION:
                # Keep it trimmed
                while len(conversation) > MAX_CONVERSATION:
                    conversation.pop(0)
                    
            return final_reply, (tokens1 + tokens2)
        else:
            # Normal text response
            reply = message_obj["content"]
            if reply is None:
                reply = ""
            reply = sanitize_reply(reply)
            
            tokens = data.get("usage", {}).get("total_tokens", 0)
            total_tokens += tokens
            conversation.append({"role": "assistant", "content": reply})
            
            return reply, tokens
            
    except Exception as exc:
        err_msg = str(exc)
        if hasattr(exc, "response") and exc.response is not None:
            try:
                err_msg += f"\nResponse body: {exc.response.text}"
            except Exception:
                pass
        
        print(f"[JARVIS] Groq API Error: {err_msg}")
        with open("groq_error.log", "w") as f:
            f.write(err_msg)
            
        # Remove the failed user message
        if conversation and conversation[-1]["role"] == "user":
            conversation.pop()
        return "I encountered a connection error while reaching my brain.", 0


# ── STT (Whisper) ───────────────────────────────────────────
def transcribe_audio(audio_bytes: bytes) -> str | None:
    if LOCAL_WHISPER_ENABLED and whisper_model is not None:
        try:
            print("[JARVIS] Using local faster-whisper...")
            # faster-whisper needs a file or a file-like object, it can't take raw bytes easily
            # We'll save bytes to a temp file and read it
            fd, temp_path = tempfile.mkstemp(suffix=".webm")
            os.close(fd)
            with open(temp_path, "wb") as f:
                f.write(audio_bytes)
            
            segments, info = whisper_model.transcribe(temp_path, beam_size=5)
            text = " ".join([segment.text for segment in segments])
            
            try:
                os.remove(temp_path)
            except:
                pass
            
            return text.strip() or None
        except Exception as e:
            print(f"[JARVIS] Local Whisper Error: {e}, falling back to Groq...")
            pass # Fallback to Groq

    if not GROQ_KEY:
        return None
    try:
        print("[JARVIS] Using Groq Whisper API...")
        resp = requests.post(
            GROQ_STT_URL,
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            files={"file": ("audio.webm", audio_bytes, "audio/webm")},
            data={"model": GROQ_STT_MODEL, "language": "en"},
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json().get("text", "").strip()
        return text or None
    except Exception:
        return None


# ── TTS ───────────────────────────────────────────────────────────
def _pocket_tts_available() -> bool:
    try:
        r = requests.get(f"{POCKET_TTS_URL}/health", timeout=0.5)
        return r.status_code == 200
    except Exception:
        return False


def _pocket_tts_synthesize(text: str) -> bytes | None:
    if not VOICE_WAV.exists():
        return None
    try:
        with open(VOICE_WAV, "rb") as f:
            resp = requests.post(
                f"{POCKET_TTS_URL}/tts",
                data={"text": text},
                files={"voice_wav": (VOICE_WAV.name, f, "audio/wav")},
                timeout=60,
            )
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None


def _groq_tts_synthesize(text: str) -> bytes | None:
    """Use Groq's TTS API (PlayAI voices) as cloud fallback."""
    if not GROQ_KEY:
        return None
    try:
        resp = requests.post(
            GROQ_TTS_URL,
            headers={
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_TTS_MODEL,
                "input": text,
                "voice": GROQ_TTS_VOICE,
                "response_format": "wav",
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None


async def _edge_tts_synthesize_async(text: str) -> bytes | None:
    """Fallback: local Edge TTS to mp3 bytes using native async API (much faster)."""
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, "en-GB-RyanNeural", rate="-0%", pitch="-5Hz")
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data
    except Exception as e:
        print(f"Edge TTS error: {e}")
        return None


async def synthesize_speech(text: str, voice_pref: str = "sapi5") -> tuple[bytes | None, str | None]:
    """Try TTS in order based on preference."""
    if voice_pref in ["edge", "sapi5"]:
        result = await _edge_tts_synthesize_async(text)
        if result:
            return result, "audio/mpeg"
            
    # 1. Pocket TTS voice cloning (if server running on 8001)
    if _pocket_tts_available():
        result = _pocket_tts_synthesize(text)
        if result:
            return result, "audio/wav"
    # 2. Local edge-tts fallback (RyanNeural - sounds like Jarvis)
    result = await _edge_tts_synthesize_async(text)
    if result:
        return result, "audio/mpeg"
    # 3. Groq cloud TTS (slowest, use as last resort)
    result = _groq_tts_synthesize(text)
    if result:
        return result, "audio/wav"
    # 3. Local edge-tts fallback (RyanNeural - sounds like Jarvis)
    result = _edge_tts_synthesize(text)
    if result:
        return result, "audio/mpeg"
    return None, None


# ══════════════════════════════════════════════════════════════════
#  FastAPI App
# ══════════════════════════════════════════════════════════════════
app = FastAPI(title="JARVIS AI v2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CommandRequest(BaseModel):
    text: str
    model: str = GROQ_LLM_MODEL
    voice: str = "sapi5"


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "groq_connected": bool(GROQ_KEY),
        "model": GROQ_LLM_MODEL,
        "stt_model": GROQ_STT_MODEL,
        "voice_wav": str(VOICE_WAV) if VOICE_WAV.exists() else None,
        "pocket_tts": _pocket_tts_available(),
        "time": datetime.now().strftime("%I:%M %p"),
    }


@app.get("/api/state")
def state():
    return {
        "brain": {
            "enabled": True,
            "available": bool(GROQ_KEY),
            "provider": "groq",
            "model": GROQ_LLM_MODEL,
        },
        "voice": {
            "stt": "Groq Whisper" if GROQ_KEY else "Browser",
            "tts": "Pocket TTS" if _pocket_tts_available() else "Groq TTS" if GROQ_KEY else "SAPI5",
            "voice_file": VOICE_WAV.name if VOICE_WAV.exists() else None,
        },
        "tokens": total_tokens,
        "conversation_length": len(conversation),
    }


# Session persistence
SESSION_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
HISTORY_FILE = BASE_DIR / "history.json"

def save_history():
    history = []
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
        except Exception:
            pass
    
    # Update current session
    session = next((s for s in history if s["id"] == SESSION_ID), None)
    if not session:
        session = {"id": SESSION_ID, "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "preview": "", "messages": []}
        history.insert(0, session)
        
    session["messages"] = conversation
    if len(conversation) > 0:
        for msg in conversation:
            if msg["role"] == "user":
                session["preview"] = msg["content"][:40] + "..."
                break
                
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

@app.get("/api/history")
def get_history():
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
            return history
        except Exception:
            return []
    return []

def _fast_intent(text: str) -> dict | None:
    """Resolve common open/close/search requests fast to bypass LLM."""
    import re
    from jarvis.core import tools
    
    raw = (text or "").strip()
    if not raw:
        return None
    lowered = f" {raw.lower()} "

    close = any(w in lowered for w in (" close ", " quit ", " exit ", " shut down ", " turn off "))
    search = any(w in lowered for w in (" search", "search ", " look up", "look up ", " find ", " search for", "search the web"))
    openv = any(w in lowered for w in (" open ", "open ", " launch ", "launch ", " start ", "start ", " go to ", " visit ", " watch ", " play ", " show me ", " bring up ", " take me to ", " navigate to "))

    if close: action = "close"
    elif search: action = "search"
    elif openv: action = "open"
    else: return None

    # LeetCode hijacking
    if "leetcode" in lowered and any(word in lowered for word in ["status", "progress", "next", "revision", "revise", "due", "mark", "solved", "done", "finished"]):
        return None

    if action == "open":
        prob_num_match = re.search(r"(?:open\s+)?(?:leetcode\s+)?(?:problem\s+(?:number\s+)?|#)(\d+)", lowered)
        if prob_num_match:
            num = prob_num_match.group(1)
            return {"response": f"Opening Leetcode problem #{num}.", "tool": "leetcode_action", "args": {"action": "open", "query": num}}
        prob_name_match = re.search(r"leetcode\s+(?:problem\s+)?([a-z0-9 ]+)$", lowered.strip().replace("  ", " "))
        if prob_name_match:
            name = prob_name_match.group(1).strip()
            return {"response": f"Opening Leetcode problem '{name}'.", "tool": "leetcode_action", "args": {"action": "open", "query": name}}

    KNOWN_WEBSITES = {
        "youtube": "https://www.youtube.com", "google": "https://www.google.com",
        "github": "https://github.com", "gmail": "https://mail.google.com",
        "chatgpt": "https://chat.openai.com", "claude": "https://claude.ai",
        "leetcode": "https://leetcode.com"
    }
    
    for name, url in KNOWN_WEBSITES.items():
        if re.search(rf"\b{name}\b", lowered):
            if action == "close":
                return {"response": f"I cannot close a browser tab directly, but I can reopen {name} anytime."}
            if action == "search":
                return {"response": f"Searching the web for {name}.", "tool": "web_search", "args": {"query": name}}
            tools.open_app(url)
            return {"response": f"Opening {name}."}

    KNOWN_APPS = {
        "calculator": "calc", "calc": "calc", "notepad": "notepad",
        "explorer": "explorer", "vscode": "vscode", "vs code": "vscode",
        "chrome": "chrome"
    }

    for name, target in KNOWN_APPS.items():
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            if action == "close":
                tools.close_app(target)
                return {"response": f"Closing {name}."}
            tools.open_app(target)
            return {"response": f"Opening {name}."}

    url_match = re.search(r"(https?://[^\s]+)|([a-z0-9-]+\.(?:com|org|net|io|dev|edu|gov|co)\b)", lowered)
    if url_match and action in {"open", "search"}:
        url = url_match.group(0)
        if action == "search":
            return {"response": f"Searching the web for {url}.", "tool": "web_search", "args": {"query": url}}
        tools.open_app(url)
        return {"response": f"Opening {url}."}

    return None


def _fast_intent(text: str) -> dict | None:
    """Resolve common open/close/search requests fast to bypass LLM."""
    import re
    from jarvis.core import tools
    
    raw = (text or "").strip()
    if not raw:
        return None
    lowered = f" {raw.lower()} "

    close = any(w in lowered for w in (" close ", " quit ", " exit ", " shut down ", " turn off "))
    search = any(w in lowered for w in (" search", "search ", " look up", "look up ", " find ", " search for", "search the web"))
    openv = any(w in lowered for w in (" open ", "open ", " launch ", "launch ", " start ", "start ", " go to ", " visit ", " watch ", " play ", " show me ", " bring up ", " take me to ", " navigate to "))

    if close: action = "close"
    elif search: action = "search"
    elif openv: action = "open"
    else: return None

    # LeetCode hijacking
    if "leetcode" in lowered and any(word in lowered for word in ["status", "progress", "next", "revision", "revise", "due", "mark", "solved", "done", "finished"]):
        return None

    if action == "open":
        prob_num_match = re.search(r"(?:open\s+)?(?:leetcode\s+)?(?:problem\s+(?:number\s+)?|#)(\d+)", lowered)
        if prob_num_match:
            num = prob_num_match.group(1)
            return {"response": f"Opening Leetcode problem #{num}.", "tool": "leetcode_action", "args": {"action": "open", "query": num}}
        prob_name_match = re.search(r"leetcode\s+(?:problem\s+)?([a-z0-9 ]+)$", lowered.strip().replace("  ", " "))
        if prob_name_match:
            name = prob_name_match.group(1).strip()
            return {"response": f"Opening Leetcode problem '{name}'.", "tool": "leetcode_action", "args": {"action": "open", "query": name}}

    KNOWN_WEBSITES = {
        "youtube": "https://www.youtube.com", "google": "https://www.google.com",
        "github": "https://github.com", "gmail": "https://mail.google.com",
        "chatgpt": "https://chat.openai.com", "claude": "https://claude.ai",
        "leetcode": "https://leetcode.com"
    }
    
    for name, url in KNOWN_WEBSITES.items():
        if re.search(rf"\b{name}\b", lowered):
            if action == "close":
                return {"response": f"I cannot close a browser tab directly, but I can reopen {name} anytime."}
            if action == "search":
                return {"response": f"Searching the web for {name}.", "tool": "web_search", "args": {"query": name}}
            tools.open_app(url)
            return {"response": f"Opening {name}."}

    KNOWN_APPS = {
        "calculator": "calc", "calc": "calc", "notepad": "notepad",
        "explorer": "explorer", "vscode": "vscode", "vs code": "vscode",
        "chrome": "chrome"
    }

    for name, target in KNOWN_APPS.items():
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            if action == "close":
                tools.close_app(target)
                return {"response": f"Closing {name}."}
            tools.open_app(target)
            return {"response": f"Opening {name}."}

    url_match = re.search(r"(https?://[^\s]+)|([a-z0-9-]+\.(?:com|org|net|io|dev|edu|gov|co)\b)", lowered)
    if url_match and action in {"open", "search"}:
        url = url_match.group(0)
        if action == "search":
            return {"response": f"Searching the web for {url}.", "tool": "web_search", "args": {"query": url}}
        tools.open_app(url)
        return {"response": f"Opening {url}."}

    return None

@app.post("/api/command")
def command(payload: CommandRequest):
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty command")

    def stream_generator():
        global total_tokens

        fast_res = _fast_intent(text)
        if fast_res:
            import json
            yield f"data: {json.dumps({'chunk': fast_res['response']})}\n\n"
            if "tool" in fast_res:
                from jarvis.core import tools
                try:
                    tools._dispatch_tool(fast_res["tool"], fast_res["args"])
                except Exception as e:
                    print("Fast intent tool error:", e)
            
            # Record in conversation
            conversation.append({"role": "user", "content": text})
            conversation.append({"role": "assistant", "content": fast_res['response']})
            save_history()
            yield f"data: {json.dumps({'done': True, 'model': 'fast_intent'})}\n\n"
            return

        if not GROQ_KEY:
            yield f"data: {json.dumps({'error': 'Groq API key not found.'})}\n\n"
        conversation.append({"role": "user", "content": text})
        if len(conversation) > MAX_CONVERSATION:
            conversation.pop(0)
            conversation.pop(0)
            
        save_history()

        system_msg = get_system_prompt()
        try:
            from jarvis.core import tools
            memories = tools.recall_memories(text)
            if memories:
                system_msg += "\n\nRelevant memories about the user:\n- " + "\n- ".join(memories)
        except Exception as e:
            print(f"[JARVIS] Memory recall error: {e}")

        messages = [{"role": "system", "content": system_msg}] + conversation
        
        # Merge dynamic tools
        dynamic_json_path = BASE_DIR / "dynamic_schemas.json"
        active_tools = list(tools.GROQ_TOOLS)
        if dynamic_json_path.exists():
            try:
                with open(dynamic_json_path, "r", encoding="utf-8") as f:
                    dynamic_schemas = json.load(f)
                    active_tools.extend(dynamic_schemas)
            except Exception:
                pass

        # Check if model is local
        is_local = "local" in payload.model.lower() or "ollama" in payload.model.lower()
        
        req_payload = {
            "model": payload.model.replace("local-", ""),
            "messages": messages,
            "temperature": 0.7,
            "stream": True
        }
        
        if not is_local:
            req_payload["tools"] = active_tools
            req_payload["tool_choice"] = "auto"
            req_payload["max_tokens"] = 512
            
            for turn_idx in range(5):
                req_payload["messages"] = [{"role": "system", "content": get_system_prompt()}] + conversation
                try:
                    resp = requests.post(
                        GROQ_LLM_URL,
                        headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                        json=req_payload,
                        stream=True,
                        timeout=20
                    )
                    
                    if resp.status_code == 400:
                        try:
                            error_data = resp.json()
                            if "tool_use_failed" in str(error_data):
                                print("[JARVIS] Groq tool error, retrying without tools.")
                                req_payload.pop("tools", None)
                                req_payload.pop("tool_choice", None)
                                resp = requests.post(
                                    GROQ_LLM_URL,
                                    headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                                    json=req_payload,
                                    stream=True,
                                    timeout=20
                                )
                        except Exception:
                            pass

                    resp.raise_for_status()
                except Exception as e:
                    yield f"data: {json.dumps({'error': f'Groq API error: {e}'})}\n\n"
                    return
                    
                tool_calls_buffer = {}
                full_text = ""
                is_tool_call = False
                
                for line in resp.iter_lines():
                    if not line:
                        continue
                    decoded = line.decode('utf-8')
                    if decoded.startswith("data: "):
                        data_str = decoded[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                        except Exception as e:
                            continue
                            
                        if "tool_calls" in delta and delta["tool_calls"]:
                            is_tool_call = True
                            for tc in delta["tool_calls"]:
                                idx = tc["index"]
                                if idx not in tool_calls_buffer:
                                    tool_calls_buffer[idx] = {"id": tc.get("id"), "function": {"name": "", "arguments": ""}}
                                if "function" in tc:
                                    if "name" in tc["function"]:
                                        tool_calls_buffer[idx]["function"]["name"] += tc["function"]["name"]
                                    if "arguments" in tc["function"]:
                                        tool_calls_buffer[idx]["function"]["arguments"] += tc["function"]["arguments"]
                                        
                        elif "content" in delta and delta["content"]:
                            content = delta["content"]
                            full_text += content
                            yield f"data: {json.dumps({'chunk': content})}\n\n"
                
                if is_tool_call:
                    assistant_tool_msg = {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": []
                    }
                    for tc in tool_calls_buffer.values():
                        assistant_tool_msg["tool_calls"].append({
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["function"]["name"],
                                "arguments": tc["function"]["arguments"]
                            }
                        })
                    conversation.append(assistant_tool_msg)
                    
                    for tc in tool_calls_buffer.values():
                        func_name = tc["function"]["name"]
                        try:
                            func_args = json.loads(tc["function"]["arguments"])
                        except Exception:
                            func_args = {}
                        print(f"[JARVIS] Calling tool: {func_name} with {func_args}")
                        result = tools.execute_tool(func_name, func_args)
                        print(f"[JARVIS] Tool result: {result}")
                        conversation.append({
                            "role": "tool",
                            "content": str(result),
                            "tool_call_id": tc["id"]
                        })
                    # Loop back for the next turn
                    continue
                else:
                    final_text = sanitize_reply(full_text)
                    assistant_message = {"role": "assistant", "content": final_text}
                    conversation.append(assistant_message)
                    save_history()
                    global total_tokens
                    total_tokens += len(final_text.split())
                    break
        else:
            # OLLAMA LOCAL STREAMING
            try:
                print(f"[JARVIS] Using local Ollama model: {req_payload['model']}")
                resp = requests.post(
                    OLLAMA_CHAT_URL,
                    json=req_payload,
                    stream=True,
                    timeout=15
                )
                resp.raise_for_status()
                
                full_text = ""
                for line in resp.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        full_text += content
                        yield f"data: {json.dumps({'chunk': content})}\n\n"
                        
                    if chunk.get("done"):
                        break
                        
                final_text = sanitize_reply(full_text)
                assistant_message = {"role": "assistant", "content": final_text}
                conversation.append(assistant_message)
                save_history()
                import threading
                threading.Thread(target=extract_memory_background, args=(text,), daemon=True).start()
                
            except Exception as e:
                yield f"data: {json.dumps({'error': f'Ollama error: {e}. Is Ollama running?'})}\n\n"
            
        yield f"data: {json.dumps({'done': True, 'model': req_payload['model']})}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.post("/api/trigger")
async def trigger_wakeup():
    if manager.active_connections:
        await manager.broadcast(json.dumps({"type": "wakeup"}))
    return {"status": "ok", "active_clients": len(manager.active_connections)}

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    audio_buffer = bytearray()
    
    try:
        while True:
            message = await websocket.receive()
            
            if "text" in message:
                try:
                    payload = json.loads(message["text"])
                    msg_type = payload.get("type", "")
                    
                    if msg_type == "stream_end":
                        # Process buffered audio
                        if len(audio_buffer) > 0:
                            # Save to a temp webm file and send to transcribe
                            try:
                                fd, temp_path = tempfile.mkstemp(suffix=".webm")
                                os.close(fd)
                                with open(temp_path, "wb") as f:
                                    f.write(audio_buffer)
                                
                                # Read back for transcription
                                with open(temp_path, "rb") as f:
                                    audio_bytes = f.read()
                                    
                                transcript = transcribe_audio(audio_bytes)
                                
                                # Send transcript back to client
                                await websocket.send_text(json.dumps({
                                    "type": "transcript",
                                    "text": transcript
                                }))
                                
                                os.remove(temp_path)
                            except Exception as e:
                                print(f"Audio STT processing error: {e}")
                                
                            audio_buffer.clear()
                            
                    elif msg_type == "command":
                        # Future: route command through WebSocket directly
                        pass
                except Exception as e:
                    print(f"WS Text Error: {e}")
                    
            elif "bytes" in message:
                # Append binary audio chunk to buffer
                audio_buffer.extend(message["bytes"])
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        manager.disconnect(websocket)


# Proactive loop
async def proactive_loop():
    # Send a test message shortly after startup
    await asyncio.sleep(5)
    if manager.active_connections:
        test_msg = json.dumps({
            "type": "proactive",
            "text": "Sir, I have successfully initialized my visual cortex and proactive subsystems."
        })
        await manager.broadcast(test_msg)
        
    while True:
        await asyncio.sleep(180) # Check every 3 minutes
        if manager.active_connections:
            try:
                from jarvis.core import tools
                import json
                ctx = tools.get_system_context()
                clip = tools.get_clipboard()
                
                # Screen Awareness
                screen_context = 'No screen data available.'
                img_data = tools.capture_screen()
                if img_data:
                    screen_context = tools.analyze_image(img_data)
                
                sys_prompt = f"""You are JARVIS, a highly advanced autonomous AI assistant. 
You are running as a background proactive engine. 
Current System Context:
- RAM Usage: {ctx['ram_percent']}%
- CPU Usage: {ctx['cpu_percent']}%
- Clipboard: {clip[:200] if clip else 'Empty'}
- Screen Context: {screen_context}

Your job is to decide if you should proactively speak to the user.
Do not speak unless there is a VERY good reason (e.g., resources are critical, they copied an obvious error to the clipboard, or they are struggling with something on their screen).
Output ONLY valid JSON in this exact format:
{{
    "should_speak": true,
    "message": "The message to speak if true, or empty string if false"
}}
"""
                from jarvis.core.server import GROQ_KEY, GROQ_LLM_MODEL
                if GROQ_KEY:
                    import requests
                    url = 'https://api.groq.com/openai/v1/chat/completions'
                    headers = {
                        'Authorization': f'Bearer {GROQ_KEY}',
                        'Content-Type': 'application/json'
                    }
                    data = {
                        'model': GROQ_LLM_MODEL,
                        'messages': [{'role': 'system', 'content': sys_prompt}],
                        'temperature': 0.3,
                        'response_format': {'type': 'json_object'}
                    }
                    response = requests.post(url, headers=headers, json=data)
                    res = response.json()
                    response_text = res['choices'][0]['message']['content']
                    res = json.loads(response_text)
                    
                    if res.get("should_speak") and res.get("message"):
                        alert_msg = json.dumps({
                            "type": "proactive",
                            "text": res["message"]
                        })
                        await manager.broadcast(alert_msg)
                        await asyncio.sleep(300)
            except Exception as e:
                print(f"[JARVIS] Proactive loop err: {e}")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(proactive_loop())


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Transcribe uploaded audio via Groq Whisper."""
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="No audio data")

    text = transcribe_audio(audio_bytes)
    if text is None:
        raise HTTPException(status_code=500, detail="Transcription failed")

    return {"text": text}


@app.post("/api/tts")
async def tts(payload: CommandRequest):
    """Synthesize speech from text, return WAV or MP3 audio."""
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    audio_bytes, media_type = await synthesize_speech(text, voice_pref=payload.voice)
    if audio_bytes is None:
        raise HTTPException(status_code=500, detail="TTS synthesis failed")

    return Response(content=audio_bytes, media_type=media_type)

# Serve static files (mounted at root last to avoid shadowing API routes)
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


def extract_memory_background(user_text: str):
    """Quietly extracts facts from user input and saves to ChromaDB."""
    try:
        from jarvis.core import tools
        from jarvis.core.server import GROQ_KEY, GROQ_LLM_MODEL
        if not GROQ_KEY:
            return
        
        sys_prompt = f"""You are an autonomous memory extractor. 
Extract any long-term facts, preferences, or personal details about the user from the following message.
Only extract things worth remembering for months. If nothing, return empty JSON.
Output ONLY valid JSON in this exact format:
{{
    "facts": ["Fact 1", "Fact 2"]
}}
"""
        import requests
        import json
        url = 'https://api.groq.com/openai/v1/chat/completions'
        headers = {
            'Authorization': f'Bearer {GROQ_KEY}',
            'Content-Type': 'application/json'
        }
        data = {
            'model': GROQ_LLM_MODEL,
            'messages': [
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': user_text}
            ],
            'temperature': 0.1,
            'response_format': {'type': 'json_object'}
        }
        response = requests.post(url, headers=headers, json=data)
        res = response.json()
        response_text = res['choices'][0]['message']['content']
        res = json.loads(response_text)
        facts = res.get("facts", [])
        for fact in facts:
            print(f"[JARVIS] Auto-memorized: {fact}")
            tools.store_memory(fact)
    except Exception as e:
        print(f"[JARVIS] Memory extraction error: {e}")
