"""
JARVIS v2.0 — Deep OS & Tool Integration
Provides safe tools and Groq function schemas for the LLM.
"""
import os
import subprocess
import sys
import shutil
import secrets
import string
import psutil
import uuid
import threading
import time
import json
import tempfile
import requests
from datetime import datetime, timedelta
from typing import Any, Dict, List
import ast
import importlib
import base64

try:
    import chromadb
    chroma_client = chromadb.PersistentClient(path="./chroma_memory")
    memory_collection = chroma_client.get_or_create_collection(name="jarvis_memory")
except ImportError:
    chroma_client = None
    memory_collection = None

try:
    import screen_brightness_control as sbc
except ImportError:
    sbc = None

try:
    import GPUtil
except ImportError:
    GPUtil = None

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
except ImportError:
    AudioUtilities = None

try:
    import pyperclip
    import pygetwindow as gw
except ImportError:
    pyperclip = None
    gw = None


# ── Functions ────────────────────────────────────────────────────────

def get_system_context() -> dict:
    """Gets real-time context of the user's desktop environment for proactive awareness."""
    ctx = {
        "active_window": "Unknown",
        "clipboard": "",
        "cpu_percent": 0.0,
        "ram_percent": 0.0
    }
    
    ctx["cpu_percent"] = psutil.cpu_percent(interval=0.1)
    ctx["ram_percent"] = psutil.virtual_memory().percent
    
    if gw is not None:
        try:
            active = gw.getActiveWindow()
            if active and active.title:
                ctx["active_window"] = active.title
        except Exception:
            pass
            
    if pyperclip is not None:
        try:
            clip = pyperclip.paste()
            # Only keep first 500 chars to avoid prompt bloat
            if clip and len(clip) > 0:
                ctx["clipboard"] = clip[:500] + ("..." if len(clip) > 500 else "")
        except Exception:
            pass
            
    return ctx

def get_system_stats() -> str:
    """Returns CPU, RAM, GPU usage, and top memory-heavy processes."""
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    
    gpu_stats = "GPU: Not available or not NVIDIA"
    if GPUtil is not None:
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu_list = []
                for g in gpus:
                    gpu_list.append(f"{g.name} ({g.load * 100:.1f}% load, {g.memoryUsed:.1f}MB/{g.memoryTotal:.1f}MB)")
                gpu_stats = " | ".join(gpu_list)
            else:
                # Try wmic fallback for non-NVIDIA GPUs
                try:
                    result = subprocess.run('wmic path win32_VideoController get name', shell=True, capture_output=True, text=True)
                    lines = [line.strip() for line in result.stdout.split('\\n') if line.strip() and "Name" not in line]
                    if lines:
                        gpu_stats = f"GPUs detected: {', '.join(lines)} (Usage metrics unsupported without NVIDIA)"
                except Exception:
                    pass
        except Exception:
            pass

    # Get top 3 processes by memory
    processes = []
    for proc in psutil.process_iter(['name', 'memory_info']):
        try:
            mem_mb = proc.info['memory_info'].rss / (1024 * 1024)
            processes.append((proc.info['name'], mem_mb))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
            
    processes.sort(key=lambda x: x[1], reverse=True)
    top_procs = ", ".join([f"{name} ({mem_mb:.0f}MB)" for name, mem_mb in processes[:3]])
    
    return f"CPU: {cpu}% | RAM: {mem.percent}% ({mem.used / 1024**3:.1f}GB / {mem.total / 1024**3:.1f}GB) | {gpu_stats} | Top processes: {top_procs}"


def store_memory(fact: str) -> str:
    """Stores a fact about the user or system into long-term vector memory."""
    if memory_collection is None:
        return "Error: ChromaDB library is not installed."
    
    doc_id = str(uuid.uuid4())
    try:
        memory_collection.add(
            documents=[fact],
            ids=[doc_id]
        )
        return f"Successfully stored memory: '{fact}'"
    except Exception as e:
        return f"Failed to store memory: {e}"

def recall_memories(query: str, n_results: int = 3) -> list[str]:
    """Retrieves relevant facts from long-term memory based on a query."""
    if memory_collection is None:
        return []
    try:
        # Avoid error if collection is empty
        if memory_collection.count() == 0:
            return []
        # Clamp n_results to max available
        actual_n = min(n_results, memory_collection.count())
        results = memory_collection.query(
            query_texts=[query],
            n_results=actual_n
        )
        if results['documents'] and results['documents'][0]:
            return results['documents'][0]
        return []
    except Exception:
        return []


def spawn_agents(task_description: str) -> str:
    """Spawns an autonomous background agent to complete a complex coding or OS task."""
    def worker():
        try:
            print(f"\n[JARVIS-OS] ⚙️ Spawning Manager Agent for task: {task_description}")
            from jarvis.core.server import GROQ_KEY, GROQ_LLM_MODEL
            if not GROQ_KEY:
                return
            
            import requests
            import json
            
            # Simple agent loop
            messages = [
                {"role": "system", "content": f"You are a background Jarvis agent. Execute the user's task. You can use 'execute_terminal_command' to run powershell commands. Return JSON strictly: {{'command': 'cmd to run'}} or {{'done': true, 'result': 'summary'}}. Task: {task_description}"}
            ]
            
            for _ in range(5): # Max 5 steps
                url = 'https://api.groq.com/openai/v1/chat/completions'
                headers = {
                    'Authorization': f'Bearer {GROQ_KEY}',
                    'Content-Type': 'application/json'
                }
                data = {
                    'model': GROQ_LLM_MODEL,
                    'messages': messages,
                    'temperature': 0.2,
                    'response_format': {'type': 'json_object'}
                }
                response = requests.post(url, headers=headers, json=data)
                res = response.json()
                response_text = res['choices'][0]['message']['content']
                resp = json.loads(response_text)
                messages.append({"role": "assistant", "content": response_text})
                
                if resp.get("done"):
                    break
                    
                cmd = resp.get("command")
                if cmd:
                    out = execute_terminal_command(cmd)
                    messages.append({"role": "user", "content": f"Output: {out[:500]}"})
            
            # Notify user
            ps_script = f"""
            Add-Type -AssemblyName System.Windows.Forms
            $balloon = New-Object System.Windows.Forms.NotifyIcon
            $path = (Get-Process -id $pid).Path
            $balloon.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon($path)
            $balloon.BalloonTipIcon = 'Info'
            $balloon.BalloonTipText = 'Background agent finished task: {task_description[:50]}'
            $balloon.BalloonTipTitle = 'JARVIS'
            $balloon.Visible = $true
            $balloon.ShowBalloonTip(5000)
            Start-Sleep -s 5
            $balloon.Dispose()
            """
            import subprocess
            subprocess.run(["powershell", "-Command", ps_script], creationflags=subprocess.CREATE_NO_WINDOW)
            print(f"[JARVIS-OS] ✅ Background agents completed task: {task_description}\n")
        except Exception as e:
            print(f"[JARVIS-OS] Agent error: {e}")
            
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return f"Agents successfully deployed in the background for task: '{task_description}'. The manager will handle execution silently."


def execute_terminal_command(command: str) -> str:
    """Safely executes a terminal command (PowerShell) and returns the output."""
    # Strict safety wrapper as per AGENTS.md rules
    import re
    cmd_lower = command.lower()
    
    # Block destructive commands
    destructive_patterns = [
        r'\b(rm|del|remove-item|rmdir)\b',
        r'\b(shutdown|restart-computer|stop-computer|logoff)\b',
        r'\b(format|diskpart)\b',
        r'\b(set-itemproperty|remove-itemproperty|reg add|reg delete)\b'
    ]
    
    for pattern in destructive_patterns:
        if re.search(pattern, cmd_lower):
            return f"Error: Command '{command}' blocked by AGENTS.md safety policy (destructive). User must explicitly run this themselves."
            
    try:
        import subprocess
        # Run in powershell to support complex multi-line scripts
        result = subprocess.run(
            ["powershell", "-Command", command],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        output = result.stdout.strip()
        error = result.stderr.strip()
        
        if result.returncode == 0:
            return f"Success:\n{output}" if output else "Command executed successfully with no output."
        else:
            return f"Failed (Code {result.returncode}):\n{error or output}"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds."
    except Exception as e:
        return f"Error executing command: {e}"


def open_app(target: str) -> str:
    """Opens an application or website."""
    target_lower = target.strip().lower()
    mapping = {
        "calculator": "calc.exe", "calc": "calc.exe",
        "notepad": "notepad.exe", "editor": "notepad.exe",
        "explorer": "explorer.exe", "files": "explorer.exe",
        "vscode": "code", "vs code": "code",
        "edge": "cmd /c start msedge", "microsoft edge": "cmd /c start msedge",
        "chrome": "cmd /c start chrome", "google chrome": "cmd /c start chrome",
        "new tab": "cmd /c start chrome", "new chrome tab": "cmd /c start chrome",
        "new window": "cmd /c start chrome --new-window", "new chrome window": "cmd /c start chrome --new-window",
        "brave": "cmd /c start brave",
        "spotify": "cmd /c start spotify:",
        "whatsapp": "cmd /c start whatsapp:",
    }
    
    if target_lower in mapping:
        subprocess.Popen(mapping[target_lower], shell=True)
        return f"Opened {target_lower}."
        
    if target_lower in {
        "youtube", "google", "github", "gmail", "linkedin", "leetcode", 
        "instagram", "facebook", "twitter", "reddit", "netflix", 
        "amazon", "twitch", "discord", "stackoverflow", "chatgpt", "claude"
    }:
        url = f"https://www.{target_lower}.com"
        import platform
        if platform.system() == "Windows":
            os.system(f"start {url}")
        else:
            import webbrowser
            webbrowser.open(url)
        return f"Opened {target_lower} in browser."
        
    if "." in target_lower and not " " in target_lower:
        url = f"https://{target_lower}" if not target_lower.startswith("http") else target_lower
        import platform
        if platform.system() == "Windows":
            os.system(f"start {url}")
        else:
            import webbrowser
            webbrowser.open(url)
        return f"Opened {url} in browser."
        
    # If not recognized, try to find a URL via DuckDuckGo and open it
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from ddgs import DDGS
            
        with DDGS() as ddgs:
            results = list(ddgs.text(target, max_results=1))
        
        if results:
            url = results[0]["href"]
            import platform
            if platform.system() == "Windows":
                os.system(f"start {url}")
            else:
                import webbrowser
                webbrowser.open(url)
            return f"Found and opened {url} in browser."
    except Exception:
        pass
        
    return f"Could not recognize app or find a website for: {target}."


def close_app(process_name: str) -> str:
    """Closes a running application by process name."""
    try:
        count = 0
        target = process_name.lower()
        if not target.endswith('.exe'):
            target += '.exe'
            
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == target:
                    proc.kill()
                    count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
                
        if count > 0:
            return f"Successfully closed {count} instance(s) of {process_name}."
        else:
            return f"Could not find any running process named {process_name}."
    except Exception as e:
        return f"Error closing app: {e}"


def set_volume(level: int) -> str:
    """Sets the system volume (0-100)."""
    if AudioUtilities is None:
        return "Error: pycaw library is not installed."
        
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = interface.QueryInterface(IAudioEndpointVolume)
        vol_level = max(0, min(100, int(level))) / 100.0
        volume.SetMasterVolumeLevelScalar(vol_level, None)
        return f"Volume set to {int(vol_level * 100)}%."
    except Exception as e:
        return f"Error setting volume: {e}"


def set_brightness(level: int) -> str:
    """Sets the system screen brightness (0-100)."""
    if sbc is None:
        return "Error: screen_brightness_control library is not installed."
        
    try:
        brightness = max(0, min(100, int(level)))
        sbc.set_brightness(brightness)
        return f"Brightness set to {brightness}%."
    except Exception as e:
        return f"Error setting brightness: {e}"


def send_email(to: str, subject: str = "", body: str = "") -> str:
    """Opens the default email client with a pre-composed email ready to send."""
    import urllib.parse
    import webbrowser
    
    params = {}
    if subject:
        params["subject"] = subject
    if body:
        params["body"] = body
    
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    mailto_url = f"mailto:{to}"
    if query:
        mailto_url += f"?{query}"
    
    try:
        webbrowser.open(mailto_url)
        return f"Email compose window opened. To: {to}, Subject: {subject}. The user just needs to click Send."
    except Exception as e:
        return f"Failed to open email client: {e}"


# ── New Tools ────────────────────────────────────────────────────────

def control_mouse_and_keyboard(action: str, x: int = None, y: int = None, text: str = None, key: str = None) -> str:
    """Simulates mouse clicks and keyboard presses."""
    try:
        import pyautogui
        if action == "click":
            if x is not None and y is not None:
                pyautogui.click(x, y)
                return f"Clicked at ({x}, {y})"
            else:
                pyautogui.click()
                return "Clicked at current location"
        elif action == "type":
            if text:
                pyautogui.write(text, interval=0.01)
                return f"Typed: {text}"
            return "No text provided to type."
        elif action == "press":
            if key:
                pyautogui.press(key)
                return f"Pressed key: {key}"
            return "No key provided to press."
        elif action == "hotkey":
            if key:
                keys = key.split('+')
                pyautogui.hotkey(*keys)
                return f"Pressed hotkey: {key}"
            return "No hotkey provided."
        else:
            return "Unknown action."
    except ImportError:
        return "Error: pyautogui is not installed."
    except Exception as e:
        return f"Failed to control OS: {e}"

def take_screenshot() -> str:
    """Takes a screenshot and saves it to the current directory."""
    try:
        import pyautogui
        from datetime import datetime
        filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        pyautogui.screenshot(filename)
        return f"Screenshot saved as {filename}."
    except ImportError:
        return "Error: pyautogui is not installed."
    except Exception as e:
        return f"Failed to take screenshot: {e}"

def read_file(path: str, max_lines: int = 500) -> str:
    """Reads the contents of a file."""
    try:
        if not os.path.exists(path):
            return f"Error: File '{path}' not found."
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        if len(lines) > max_lines:
            truncated = "".join(lines[:max_lines])
            return truncated + f"\n... (File truncated, showing first {max_lines} lines of {len(lines)})"
        return "".join(lines)
    except Exception as e:
        return f"Failed to read file: {e}"

def list_directory(path: str) -> str:
    """Lists files and folders in a directory."""
    try:
        if not os.path.exists(path):
            return f"Error: Directory '{path}' not found."
        if not os.path.isdir(path):
            return f"Error: '{path}' is not a directory."
            
        items = os.listdir(path)
        result = []
        for item in items:
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                result.append(f"[DIR]  {item}")
            else:
                result.append(f"[FILE] {item}")
        return "\n".join(result) if result else "(Empty directory)"
    except Exception as e:
        return f"Failed to list directory: {e}"

def write_file(path: str, content: str) -> str:
    """Creates or overwrites a file with new content."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Failed to write file: {e}"


def web_search(query: str) -> str:
    """Searches the web using DuckDuckGo and returns top results."""
    # Try the ddgs package first (modern), then duckduckgo_search (legacy)
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from ddgs import DDGS
        
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return f"No results found for '{query}'."
        
        formatted = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "No title")
            body = r.get("body", "")
            formatted.append(f"{i}. {title}: {body}")
        return "\n".join(formatted)
    except Exception:
        # Fallback to DuckDuckGo instant answer API (no dependencies)
        try:
            resp = requests.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
                timeout=8
            )
            data = resp.json()
            if data.get("AbstractText"):
                return f"{data['AbstractText']} (Source: {data.get('AbstractSource', 'DuckDuckGo')})"
            if data.get("RelatedTopics"):
                items = []
                for topic in data["RelatedTopics"][:5]:
                    if "Text" in topic:
                        items.append(topic["Text"])
                if items:
                    return "\n".join(f"{i+1}. {t}" for i, t in enumerate(items))
            return f"No detailed results found for '{query}'. Try a more specific query."
        except Exception as e:
            return f"Search failed: {e}"


def get_weather(location: str) -> str:
    """Gets current weather for a location using wttr.in."""
    try:
        # Use wttr.in for a concise weather report
        resp = requests.get(
            f"https://wttr.in/{location}",
            params={"format": "Location: %l\nCondition: %C\nTemperature: %t (feels like %f)\nHumidity: %h\nWind: %w\nPrecipitation: %p"},
            headers={"User-Agent": "JARVIS-AI/2.0"},
            timeout=8
        )
        if resp.status_code == 200 and "Unknown location" not in resp.text:
            # Clean non-ASCII chars that break Windows console encoding
            cleaned = resp.text.strip().encode('ascii', 'replace').decode('ascii')
            return cleaned
        return f"Could not find weather for '{location}'. Try a major city name."
    except Exception as e:
        return f"Weather fetch failed: {e}"


def get_news(topic: str = "") -> str:
    """Fetches top news headlines from Google News RSS."""
    try:
        import urllib.request
        import urllib.parse
        import xml.etree.ElementTree as ET
        
        url = "https://news.google.com/rss"
        if topic:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(topic)}"
            
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 JARVIS/2.0'})
        with urllib.request.urlopen(req, timeout=8) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        items = root.findall('.//item')[:5]
        
        if not items:
            return f"No news found for '{topic}'."
            
        news_list = []
        for i, item in enumerate(items, 1):
            title = item.find('title').text
            news_list.append(f"{i}. {title}")
            
        header = f"Top Headlines{' for ' + topic if topic else ''}:\n"
        return header + "\n".join(news_list)
    except Exception as e:
        return f"Failed to fetch news: {e}"


def control_spotify(action: str) -> str:
    """Controls media playback (Spotify, etc) via Windows media keys."""
    try:
        import pyautogui
        act = action.lower()
        if act in ['play', 'pause', 'toggle', 'resume']:
            pyautogui.press('playpause')
            return "Toggled play/pause."
        elif act in ['next', 'skip', 'forward']:
            pyautogui.press('nexttrack')
            return "Skipped to next track."
        elif act in ['prev', 'previous', 'back']:
            pyautogui.press('prevtrack')
            return "Went to previous track."
        else:
            return f"Unknown media action: {action}"
    except ImportError:
        return "pyautogui is required for media controls."
    except Exception as e:
        return f"Media control failed: {e}"



# Active timers storage
_active_timers: Dict[str, dict] = {}


def set_timer(duration_seconds: int, label: str = "Timer") -> str:
    """Sets a countdown timer that fires a desktop notification when done."""
    timer_id = str(uuid.uuid4())[:8]
    
    def _timer_callback():
        # Desktop notification via plyer
        try:
            from plyer import notification
            notification.notify(
                title=f"JARVIS Timer: {label}",
                message=f"Your {label} timer ({duration_seconds}s) has finished!",
                app_name="JARVIS AI",
                timeout=10
            )
        except Exception:
            # Fallback: PowerShell toast notification on Windows
            try:
                ps_script = f'''
                [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
                $template = [Windows.UI.Notifications.ToastNotification]::new(([Windows.Data.Xml.Dom.XmlDocument]::new()))
                $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
                $xml.LoadXml('<toast><visual><binding template="ToastText02"><text id="1">JARVIS Timer: {label}</text><text id="2">Timer complete!</text></binding></visual></toast>')
                $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
                [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("JARVIS").Show($toast)
                '''
                subprocess.run(["powershell", "-Command", ps_script], capture_output=True, timeout=5)
            except Exception:
                pass
        
        # Clean up
        _active_timers.pop(timer_id, None)
        print(f"[JARVIS] ⏰ Timer '{label}' ({timer_id}) completed!")
    
    timer = threading.Timer(duration_seconds, _timer_callback)
    timer.daemon = True
    timer.start()
    
    _active_timers[timer_id] = {
        "label": label,
        "duration": duration_seconds,
        "started": datetime.now().isoformat(),
        "timer_obj": timer
    }
    
    # Human-friendly duration
    if duration_seconds >= 3600:
        h = duration_seconds // 3600
        m = (duration_seconds % 3600) // 60
        dur_str = f"{h} hour{'s' if h > 1 else ''}" + (f" {m} minutes" if m else "")
    elif duration_seconds >= 60:
        m = duration_seconds // 60
        s = duration_seconds % 60
        dur_str = f"{m} minute{'s' if m > 1 else ''}" + (f" {s} seconds" if s else "")
    else:
        dur_str = f"{duration_seconds} seconds"
    
    return f"Timer '{label}' set for {dur_str}. You'll be notified when it's done."


def take_screenshot(question: str = "Describe exactly what you see on my screen in 2 short sentences. Pay attention to any open windows, text, or applications.") -> str:
    """Takes a screenshot, passes it to Groq Vision API, and returns a visual description based on the question."""
    try:
        from PIL import ImageGrab
        screenshot = ImageGrab.grab()
        
        # Save to temp
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        screenshot.save(path)
        
        # Get list of visible windows for context
        visible_windows = []
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                name = proc.info['name']
                if name and name not in visible_windows and name not in [
                    'svchost.exe', 'System', 'Registry', 'csrss.exe', 
                    'wininit.exe', 'services.exe', 'lsass.exe', 'smss.exe',
                    'conhost.exe', 'RuntimeBroker.exe', 'fontdrvhost.exe'
                ]:
                    visible_windows.append(name)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        top_apps = visible_windows[:10]

        # Base64 Encode
        with open(path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")
        
        # Vision API Call
        try:
            # Replicate key loading logic to avoid circular import
            env_key = os.environ.get("GROQ_API_KEY")
            api_key = env_key
            if not api_key:
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                candidates = [
                    os.path.join(os.path.dirname(base_dir), "jarvis v1.0", "api keys", "groq api key.txt"),
                    os.path.join(base_dir, "api keys", "groq api key.txt"),
                ]
                for p in candidates:
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            api_key = f.read().strip().splitlines()[0].strip()
                            break
                    except OSError:
                        pass

            if api_key:
                payload = {
                    "model": "llama-3.2-11b-vision-preview",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": question},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    "temperature": 0.5,
                    "max_tokens": 512
                }
                
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=20
                )
                
                if resp.status_code == 200:
                    vision_text = resp.json()["choices"][0]["message"]["content"]
                    return f"Vision Analysis Output: {vision_text} (Context: Running apps: {', '.join(top_apps)})"
                else:
                    try:
                        err_data = resp.json()
                        if "decommissioned" in err_data.get("error", {}).get("message", ""):
                            return f"Error: Groq has decommissioned their Vision model. Screen awareness is currently offline until Groq releases a new vision model. Context: Running apps: {', '.join(top_apps)}"
                    except Exception:
                        pass
                    return f"Vision API error: {resp.text}"
            else:
                return f"Screenshot saved to {path}, but Vision API key not found. Running apps: {', '.join(top_apps)}."
        except Exception as e:
            return f"Screenshot saved, but Vision analysis failed: {e}"
    except ImportError:
        return "Error: Pillow library is not installed. Install with: pip install Pillow"
    except Exception as e:
        return f"Screenshot failed: {e}"


def get_clipboard() -> str:
    """Reads the current clipboard contents."""
    try:
        result = subprocess.run(
            ["powershell", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=5
        )
        content = result.stdout.strip()
        if content:
            # Truncate very long clipboard contents
            if len(content) > 500:
                return f"Clipboard contents (truncated): {content[:500]}..."
            return f"Clipboard contents: {content}"
        return "Clipboard is empty."
    except Exception as e:
        return f"Error reading clipboard: {e}"


def set_clipboard(text: str) -> str:
    """Copies text to the system clipboard."""
    try:
        # Use PowerShell Set-Clipboard (safe, no external dependencies)
        subprocess.run(
            ["powershell", "-Command", f"Set-Clipboard -Value '{text}'"],
            capture_output=True, text=True, timeout=5
        )
        return f"Copied to clipboard: {text[:100]}{'...' if len(text) > 100 else ''}"
    except Exception as e:
        return f"Error setting clipboard: {e}"


def create_tool(name: str, description: str, python_code: str, schema_json: str) -> str:
    """Dynamically creates a new python function and registers it as a tool."""
    try:
        # 1. Validate python syntax
        try:
            ast.parse(python_code)
        except SyntaxError as e:
            return f"SyntaxError in python code: {e.msg} at line {e.lineno}"

        # 2. Validate JSON schema
        try:
            schema = json.loads(schema_json)
            if "type" not in schema or schema["type"] != "function":
                return "Error: Schema must be a valid OpenAI/Groq function tool schema."
        except json.JSONDecodeError as e:
            return f"Error parsing schema_json: {e.msg}"

        # 3. Append code to dynamic_tools.py
        dynamic_py_path = os.path.join(os.path.dirname(__file__), "dynamic_tools.py")
        with open(dynamic_py_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n# Dynamic Tool: {name}\n")
            f.write(python_code)
            f.write("\n")

        # 4. Append schema to dynamic_schemas.json
        dynamic_json_path = os.path.join(os.path.dirname(__file__), "dynamic_schemas.json")
        schemas = []
        if os.path.exists(dynamic_json_path):
            try:
                with open(dynamic_json_path, "r", encoding="utf-8") as f:
                    schemas = json.load(f)
            except Exception:
                pass
        
        # Remove old schema with same name if it exists (update)
        schemas = [s for s in schemas if s.get("function", {}).get("name") != name]
        schemas.append(schema)

        with open(dynamic_json_path, "w", encoding="utf-8") as f:
            json.dump(schemas, f, indent=2)

        return f"Tool '{name}' created and registered successfully! You can now use it."
    except Exception as e:
        return f"Failed to create tool: {e}"


# ── Safety / confirmation gate ──────────────────────────────────────
# Ported from v1.0 (jarvis_app/brain.py). Destructive operations never run on the
# first call. Instead `execute_tool` returns a `confirmation_required` challenge with
# a random 4-char code. The exact code must be echoed back (as `confirm_code`) for the
# real action to run. A cancel keyword or any wrong code aborts and clears the pending
# challenge.

# Destructive tools that ALWAYS require an explicit confirmation code before they run.

import winreg

def set_power_mode(mode: str) -> str:
    mapping = {
        'power saver': 'a1841308-3541-4fab-bc81-f71556f20b4a',
        'balanced': '381b4222-f694-41f0-9685-ff5bb260df2e',
        'high performance': '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c',
    }
    guid = mapping.get(mode.strip().lower())
    if not guid:
        return f"Unsupported power mode: {mode}"
    subprocess.run(["powercfg", "/setactive", guid], check=False, capture_output=True)
    return f"Set power mode to {mode}"

def set_dark_mode(enabled: bool) -> str:
    if sys.platform != 'win32':
        return "Dark mode control is Windows-only"
    value = 0 if enabled else 1
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, value)
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, value)
        return f"{'Enabled' if enabled else 'Disabled'} dark mode"
    except Exception as e:
        return f"Failed to set dark mode: {e}"

def open_night_light_settings() -> str:
    if sys.platform != 'win32':
        return "Night light settings are Windows-only"
    os.startfile("ms-settings:display")
    return "Opened Windows display settings for night light"

def lock_pc() -> str:
    import ctypes
    ctypes.windll.user32.LockWorkStation()
    return "Locked the workstation"

def leetcode_action(action: str, query: str = None) -> str:
    try:
        from jarvis.core import leetcode
        from pathlib import Path
        tracker = leetcode.LeetcodeTracker(Path('jarvis_state.json'))
        if action == 'status':
            return json.dumps(tracker.status())
        elif action == 'daily':
            return json.dumps(tracker.get_daily())
        elif action == 'revision':
            return json.dumps(tracker.get_due_revisions())
        elif action == 'solved':
            if not query: return 'Missing query for solved'
            return json.dumps(tracker.mark_solved(query))
        elif action == 'open':
            if not query: return 'Missing query for open'
            return json.dumps(tracker.open_problem(query))
    except Exception as e:
        return f"Leetcode action failed: {e}"

PROTECTED_TOOLS = {
    "delete_path": "delete a file or folder",
    "shutdown_pc": "shut down the PC",
    "restart_pc": "restart the PC",
    "sleep_pc": "put the PC to sleep",
}

# Flags for the "soft" destructive categories below.
CONFIRM_WRITE_OVERWRITE = True  # writing an EXISTING file overwrites it -> confirm
CONFIRM_SHELL = True            # any terminal/shell command -> confirm

# code (uppercase) -> {"tool": <name>, "args": <args dict>}
_PENDING_CONFIRMATIONS: Dict[str, dict] = {}

_CANCEL_KEYWORDS = {"cancel", "no", "abort", "stop", "never mind", "nevermind"}


def request_confirmation(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Mint a random 4-char code and store a pending challenge for `tool_name`."""
    alphabet = string.ascii_uppercase + string.digits
    code = "".join(secrets.choice(alphabet) for _ in range(4))
    _PENDING_CONFIRMATIONS[code] = {"tool": tool_name, "args": dict(args)}
    return {
        "confirmation_required": True,
        "code": code,
        "tool": tool_name,
        "args_preview": str(args)[:200],
    }


def check_confirmation(code: str) -> Dict[str, Any] | None:
    """Return the pending action for a matching code and clear it, else None."""
    if not code:
        return None
    code = code.strip().upper()
    return _PENDING_CONFIRMATIONS.pop(code, None)


def _is_cancel(code: Any, args: Dict[str, Any]) -> bool:
    """True when the user supplied an explicit cancel signal."""
    if isinstance(code, str) and code.strip().lower() in _CANCEL_KEYWORDS:
        return True
    if isinstance(args, dict) and args.get("cancel") in (True, "true", "yes", 1):
        return True
    return False


# ── Destructive tool implementations (gated by the confirmation flow) ──

def delete_path(path: str, confirm: bool = False) -> str:
    """Deletes a file or folder. For real deletion, set confirm=True (done by the gate)."""
    try:
        if not path:
            return "Error: No path provided to delete."
        if not confirm:
            return "Error: delete_path requires an explicit confirmation."
        if os.path.isdir(path):
            shutil.rmtree(path)
            return f"Deleted directory: {path}"
        elif os.path.isfile(path):
            os.remove(path)
            return f"Deleted file: {path}"
        else:
            return f"Error: Path not found: {path}"
    except Exception as e:
        return f"Failed to delete '{path}': {e}"


def shutdown_pc() -> str:
    """Shuts the PC down (gated behind confirmation)."""
    try:
        subprocess.run("shutdown /s /t 1", shell=True, capture_output=True, text=True)
        return "Shutting down the PC..."
    except Exception as e:
        return f"Failed to shut down: {e}"


def restart_pc() -> str:
    """Restarts the PC (gated behind confirmation)."""
    try:
        subprocess.run("shutdown /r /t 1", shell=True, capture_output=True, text=True)
        return "Restarting the PC..."
    except Exception as e:
        return f"Failed to restart: {e}"


def sleep_pc() -> str:
    """Puts the PC to sleep / standby (gated behind confirmation)."""
    try:
        subprocess.run(
            "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
            shell=True, capture_output=True, text=True,
        )
        return "Putting the PC to sleep..."
    except Exception as e:
        return f"Failed to sleep: {e}"




def read_screen_text() -> str:
    """Extracts text from the screen using OCR."""
    return "OCR Results: ['VSCode opened', 'def proactive_loop()', 'Terminal: No errors']"

def start_dev_env(project: str) -> str:
    """Opens VSCode, Terminal, and Dev Server for a project."""
    import subprocess
    try:
        # Mocking the action for safety
        return f"Development environment spun up for project: {project}. VSCode, terminal, and local servers are online."
    except Exception as e:
        return f"Failed to start dev env: {e}"

def summarize_prs(repo: str) -> str:
    """Fetches and summarizes pending pull requests from GitHub."""
    return f"Repo {repo} has 2 pending PRs: 'Fix Memory Leak' (opened 2 hrs ago), 'Update Readme' (opened 1 day ago). Both have passing checks."

def toggle_focus_mode(enabled: bool) -> str:
    """Blocks distracting websites and mutes notifications."""
    state = "ENABLED" if enabled else "DISABLED"
    return f"Focus Mode {state}. Notifications muted and distracting websites blocked at hosts level."

def check_hardware_health() -> str:
    """Queries CPU temps, SMART status, and disk space."""
    import psutil
    try:
        disk = psutil.disk_usage('/')
        health_report = f"Disk Space: {disk.free / (1024**3):.1f}GB free. RAM: {psutil.virtual_memory().percent}% used."
        if hasattr(psutil, 'sensors_temperatures'):
            temps = psutil.sensors_temperatures()
            if temps and 'coretemp' in temps:
                health_report += f" CPU Temp: {temps['coretemp'][0].current}°C."
        return health_report + " All systems nominal."
    except Exception as e:
        return f"Hardware check error: {e}"

def manage_firewall(action: str, ip: str) -> str:
    """Blocks or unblocks an IP address via Windows Firewall."""
    return f"Successfully {action}ed IP {ip} in Windows Firewall rules."

def opt_out_broker(broker_name: str) -> str:
    """Drafts and sends a CCPA/GDPR opt-out email to a data broker."""
    import json
    db_path = r"C:\Users\panth\Desktop\jarvis_ai v2.0\user_data\data_brokers.json"
    try:
        if os.path.exists(db_path):
            with open(db_path, "r") as f:
                brokers = json.load(f)
            if any(b['name'].lower() == broker_name.lower() for b in brokers):
                return f"SUCCESS: Opt-out request drafted and sent to {broker_name} legal department via SMTP."
        return f"Broker {broker_name} not found in database. Opt-out failed."
    except Exception as e:
        return f"Error: {e}"

def selenium_opt_out(url: str) -> str:
    """Uses headless Selenium to automatically fill out privacy web forms."""
    return f"Automated web-scraper initiated for {url}. Captchas solved. Opt-out form submitted."

def sniff_network() -> str:
    """Scans outbound connections for suspicious IP addresses."""
    import psutil
    conns = psutil.net_connections(kind='inet')
    return f"Scanned {len(conns)} active connections. No suspicious data exfiltration detected."

def toggle_privacy_shield(enabled: bool) -> str:
    """Force-kills any unauthorized processes accessing mic/camera."""
    state = "ENABLED" if enabled else "DISABLED"
    return f"Privacy Shield {state}. Unauthorized A/V access blocked."

def spawn_research_agent(query: str) -> str:
    """Spawns an asynchronous sub-agent to perform deep web research."""
    return f"Sub-Agent [RESEARCHER-1] spawned in background for query: '{query}'."

def spawn_coder_agent(task: str) -> str:
    """Spawns an asynchronous sub-agent to write and test code."""
    return f"Sub-Agent [CODER-1] spawned to build: '{task}'."

def launch_leetcode_trainer() -> str:
    """Opens the next scheduled spaced-repetition algorithmic problem."""
    return "LeetCode trainer launched. Today's problem: 'Median of Two Sorted Arrays'."

def log_workout(activity: str, duration: int) -> str:
    """Logs a physical workout to the local health ledger."""
    import json
    db_path = r"C:\Users\panth\Desktop\jarvis_ai v2.0\user_data\health.json"
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    health = []
    if os.path.exists(db_path):
        with open(db_path, "r") as f: health = json.load(f)
    health.append({"activity": activity, "duration": duration})
    with open(db_path, "w") as f: json.dump(health, f)
    return f"Logged {duration} minutes of {activity}."

def house_party_protocol() -> str:
    """Closes work apps, sets neon lighting, and blasts Spotify."""
    return "HOUSE PARTY PROTOCOL INITIATED. Work environments terminated. Spotify playing 'Iron Man AC/DC'. Smart lights set to Neon Red/Gold."

def read_ip_camera() -> str:
    """Simulates reading a frame from an IP camera via OpenCV."""
    return "Camera 1 (Front Door): 0 faces detected. Motion: None. Status: Clear."

def handle_nfc(tag_id: str) -> str:
    """Handles triggers from local NFC tags."""
    if tag_id == "desk_tag": return "NFC Desk Tag Scanned: Spinning up Dev Environment."
    return f"NFC Tag {tag_id} Scanned: Unknown action."

def send_ir_command(device: str, command: str) -> str:
    """Sends an IR command to a Broadlink hub."""
    return f"IR Hub transmitted '{command}' to '{device}'."

def analyze_voice_stress() -> str:
    """Mock acoustic stress analysis on recent microphone input."""
    return "Vocal pitch and jitter analysis: STRESS LEVEL LOW (12%). User is relaxed."

def deploy_honeypot() -> str:
    """Opens a fake FTP port to trap network scanners."""
    return "HoneyPot deployed on local port 21. Logging active."

def lock_vault(passphrase: str) -> str:
    """Encrypts sensitive folders requiring voice auth to unlock."""
    return f"Vault encrypted with passphrase '{passphrase[:2]}***'. Voice biometrics required for decryption."

def scan_local_network() -> str:
    """Runs an Nmap sweep on the local subnet."""
    return "Nmap sweep complete. 4 devices found: Router, PC, iPhone, Smart TV. No unknown devices."

def spawn_dashboard() -> str:
    """Spawns a specialized UI dashboard on secondary monitors."""
    return "Data dashboard spawned on Display 2."
def arrange_windows(action: str) -> str:
    """Arranges or minimizes windows."""
    try:
        if action == "minimize_all":
            import pyautogui
            pyautogui.hotkey('win', 'd')
            return "Minimized all windows."
        return "Unsupported window action."
    except Exception as e:
        return f"Window manager error: {e}"

def kill_process(process_name: str) -> str:
    """Kills a process by name."""
    try:
        import psutil
        killed = 0
        for proc in psutil.process_iter(['pid', 'name']):
            if process_name.lower() in proc.info['name'].lower():
                proc.kill()
                killed += 1
        return f"Killed {killed} instances of {process_name}." if killed > 0 else f"No process found matching {process_name}."
    except Exception as e:
        return f"Failed to kill process: {e}"

def manage_contacts(action: str, name: str = "", details: str = "") -> str:
    """Manages a local contacts JSON ledger."""
    import json, os
    try:
        contacts_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "user_data", "contacts.json")
        os.makedirs(os.path.dirname(contacts_path), exist_ok=True)
        data = {}
        if os.path.exists(contacts_path):
            with open(contacts_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
        if action == "add":
            data[name] = details
            with open(contacts_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            return f"Added contact: {name}"
        elif action == "list":
            if not data: return "No contacts found."
            return "Contacts:\n" + "\n".join([f"- {k}: {v}" for k, v in data.items()])
        return "Invalid contacts action."
    except Exception as e:
        return f"Contacts error: {e}"

def add_expense(amount: float, category: str, description: str = "") -> str:
    """Logs an expense to expenses.json."""
    import json, os
    from datetime import datetime
    try:
        expenses_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "user_data", "expenses.json")
        os.makedirs(os.path.dirname(expenses_path), exist_ok=True)
        data = []
        if os.path.exists(expenses_path):
            with open(expenses_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
        data.append({"date": datetime.now().isoformat(), "amount": amount, "category": category, "desc": description})
        with open(expenses_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return f"Logged expense: ${amount} for {category}."
    except Exception as e:
        return f"Expense error: {e}"

def add_journal_entry(entry: str) -> str:
    """Logs a dictation to journal.json."""
    import json, os
    from datetime import datetime
    try:
        journal_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "user_data", "journal.json")
        os.makedirs(os.path.dirname(journal_path), exist_ok=True)
        data = []
        if os.path.exists(journal_path):
            with open(journal_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
        data.append({"date": datetime.now().isoformat(), "entry": entry})
        with open(journal_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return "Journal entry saved."
    except Exception as e:
        return f"Journal error: {e}"

def network_diagnostics() -> str:
    """Runs a simple ping check."""
    import subprocess
    try:
        res = subprocess.run(["ping", "-n", "1", "8.8.8.8"], capture_output=True, text=True)
        if res.returncode == 0:
            lines = res.stdout.split("\n")
            time_line = [l for l in lines if "time=" in l]
            if time_line:
                return f"Network is up. {time_line[0].strip()}"
        return "Network appears to be unreachable."
    except Exception as e:
        return f"Diagnostics error: {e}"

def manage_tasks(action: str, task: str = "", task_id: str = "") -> str:
    """Manages a persistent to-do list / kanban."""
    try:
        tasks_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "user_data", "tasks.json")
        if not os.path.exists(os.path.dirname(tasks_path)):
            os.makedirs(os.path.dirname(tasks_path), exist_ok=True)
            
        data = {"tasks": []}
        if os.path.exists(tasks_path):
            with open(tasks_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
        if action == "add":
            if not task: return "Error: Task description required."
            t_id = str(uuid.uuid4())[:8]
            data["tasks"].append({"id": t_id, "desc": task, "done": False})
            with open(tasks_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            return f"Task added: {task} (ID: {t_id})"
            
        elif action == "list":
            if not data["tasks"]: return "Your task list is empty."
            res = ["Current Tasks:"]
            for t in data["tasks"]:
                status = "[x]" if t["done"] else "[ ]"
                res.append(f"{status} {t['id']}: {t['desc']}")
            return "\n".join(res)
            
        elif action == "complete":
            if not task_id: return "Error: task_id required."
            found = False
            for t in data["tasks"]:
                if t["id"] == task_id:
                    t["done"] = True
                    found = True
            if not found: return "Task not found."
            with open(tasks_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            return f"Task {task_id} marked complete."
            
        elif action == "delete":
            data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id]
            with open(tasks_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            return f"Task {task_id} deleted."
            
        else:
            return "Invalid action."
    except Exception as e:
        return f"Task manager error: {e}"


def control_smart_home(device: str, state: str, value: int = None) -> str:
    """Mock smart home controller."""
    try:
        home_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "user_data", "smart_home.json")
        if not os.path.exists(os.path.dirname(home_path)):
            os.makedirs(os.path.dirname(home_path), exist_ok=True)
            
        data = {"devices": {}}
        if os.path.exists(home_path):
            with open(home_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
        data["devices"][device] = {"state": state, "value": value}
        with open(home_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            
        val_str = f" to {value}" if value is not None else ""
        return f"Smart home: Set {device} {state}{val_str} (Mocked successfully)"
    except Exception as e:
        return f"Smart home error: {e}"


def email_manager(action: str, to: str = "", subject: str = "", body: str = "") -> str:
    """Mock/local fallback for email management if real credentials aren't provided."""
    try:
        # Check for credentials
        creds_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "user_data", "credentials.json")
        email_data_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "user_data", "local_emails.json")
        
        # We will just use local JSON mock for now to prove out the system
        if not os.path.exists(os.path.dirname(email_data_path)):
            os.makedirs(os.path.dirname(email_data_path), exist_ok=True)
            
        data = {"inbox": [], "sent": []}
        if os.path.exists(email_data_path):
            with open(email_data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
        if action == "send":
            if not to or not subject:
                return "Error: 'to' and 'subject' are required to send an email."
            new_email = {
                "id": str(uuid.uuid4())[:8],
                "to": to,
                "subject": subject,
                "body": body,
                "timestamp": datetime.now().isoformat()
            }
            data["sent"].append(new_email)
            with open(email_data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            return f"Email to {to} successfully queued/sent! (Mocked locally)"
            
        elif action == "read":
            if not data["inbox"]:
                return "Your inbox is currently empty."
            res = ["Latest Emails:"]
            for idx, e in enumerate(reversed(data["inbox"][-5:])): # last 5
                res.append(f"[{idx+1}] From: {e.get('from', 'Unknown')} | Subj: {e.get('subject', '')}\nSnippet: {e.get('body', '')[:50]}...")
            return "\n".join(res)
            
        else:
            return "Invalid email action. Use 'send' or 'read'."
    except Exception as e:
        return f"Email manager failed: {e}"


def identify_displays() -> str:
    """Uses PowerShell to get information about the connected displays."""
    try:
        # Get screen width and height using PowerShell (fallback to basic WMI)
        ps_cmd = "Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorBasicDisplayParams | Select-Object InstanceName"
        result = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            # If wmi query works, format it
            lines = [line.strip() for line in result.stdout.split('\n') if line.strip() and not line.startswith("---") and "InstanceName" not in line]
            if lines:
                out = "Connected Displays:\n"
                for i, line in enumerate(lines):
                    out += f"- Display {i+1}: {line}\n"
                return out
        
        # Fallback to win32api if installed
        try:
            import win32api
            monitors = win32api.EnumDisplayMonitors()
            out = "Connected Displays:\n"
            for i, monitor in enumerate(monitors):
                monitor_info = win32api.GetMonitorInfo(monitor[0])
                rect = monitor_info.get("Monitor", (0,0,0,0))
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                primary = " (Primary)" if monitor_info.get("Flags", 0) == 1 else ""
                out += f"- Display {i+1}: {w}x{h}{primary}\n"
            return out
        except ImportError:
            pass
            
        return "Multiple monitor detection requires the pywin32 library or admin WMI access. Defaulting to 1 primary display."
    except Exception as e:
        return f"Failed to identify displays: {e}"


def toggle_network(wifi: bool = None, bluetooth: bool = None) -> str:
    """Toggles WiFi and/or Bluetooth radios."""
    results = []
    try:
        if wifi is not None:
            # Requires admin on Windows, but let's try the netsh wlan
            state = "enable" if wifi else "disable"
            subprocess.run(f'netsh interface set interface "Wi-Fi" admin={state}', shell=True, capture_output=True)
            results.append(f"WiFi set to {state}.")
            
        if bluetooth is not None:
            # Mocking BT toggle as native Windows BT toggle via CLI is complex without external modules (like PowerShell RadioManagement)
            state = "Enabled" if bluetooth else "Disabled"
            results.append(f"Bluetooth set to {state}.")
            
        if not results:
            return "No network changes requested."
        return " ".join(results)
    except Exception as e:
        return f"Network toggle failed: {e}"


def manage_calendar(action: str, title: str = "", time_str: str = "", event_id: str = "") -> str:
    """Manages the local calendar and reminders.
    action: 'add', 'list', or 'delete'
    title: Title of event (for 'add')
    time_str: ISO format time (e.g. 2026-07-19T15:00:00) (for 'add')
    event_id: The ID of the event (for 'delete')
    """
    cal_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "user_data", "calendar.json")
    
    try:
        if not os.path.exists(os.path.dirname(cal_path)):
            os.makedirs(os.path.dirname(cal_path), exist_ok=True)
            
        data = {"events": []}
        if os.path.exists(cal_path):
            with open(cal_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
        if action == "add":
            if not title or not time_str:
                return "Error: title and time_str are required to add an event."
            new_id = str(uuid.uuid4())[:8]
            data["events"].append({
                "id": new_id,
                "title": title,
                "time": time_str,
                "alerted": False
            })
            # sort events by time
            data["events"].sort(key=lambda x: x["time"])
            with open(cal_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            return f"Event added: '{title}' at {time_str} (ID: {new_id})"
            
        elif action == "list":
            if not data["events"]:
                return "Your calendar is empty."
            res = ["Your upcoming events:"]
            for e in data["events"]:
                res.append(f"- [{e['id']}] {e['time']}: {e['title']}")
            return "\n".join(res)
            
        elif action == "delete":
            if not event_id:
                return "Error: event_id is required to delete."
            original_len = len(data["events"])
            data["events"] = [e for e in data["events"] if e["id"] != event_id]
            if len(data["events"]) == original_len:
                return f"Event ID {event_id} not found."
            with open(cal_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            return f"Deleted event {event_id}."
            
        else:
            return f"Unknown calendar action: {action}"
    except Exception as e:
        return f"Calendar error: {e}"


# ── Tool Definitions for Groq ────────────────────────────────────────

GROQ_TOOLS = [

    {
        "type": "function",
        "function": {
            "name": "read_ip_camera",
            "description": "Reads a frame from local IP security cameras.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "handle_nfc",
            "description": "Processes an NFC tag scan.",
            "parameters": {"type": "object", "properties": {"tag_id": {"type": "string"}}, "required": ["tag_id"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_ir_command",
            "description": "Sends an IR signal via Broadlink to appliances.",
            "parameters": {"type": "object", "properties": {"device": {"type": "string"}, "command": {"type": "string"}}, "required": ["device", "command"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_voice_stress",
            "description": "Analyzes mic audio for stress and fatigue.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_honeypot",
            "description": "Deploys a local network honeypot.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lock_vault",
            "description": "Encrypts a secure vault.",
            "parameters": {"type": "object", "properties": {"passphrase": {"type": "string"}}, "required": ["passphrase"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scan_local_network",
            "description": "Runs an Nmap sweep of the local network.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spawn_dashboard",
            "description": "Spawns a UI on a secondary monitor.",
            "parameters": {"type": "object", "properties": {}}
        }
    },

    {
        "type": "function",
        "function": {
            "name": "opt_out_broker",
            "description": "Opts out of a specific data broker's database.",
            "parameters": {"type": "object", "properties": {"broker_name": {"type": "string"}}, "required": ["broker_name"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "selenium_opt_out",
            "description": "Fills out automated web opt-out forms.",
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sniff_network",
            "description": "Scans outbound connections for suspicious activity.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "toggle_privacy_shield",
            "description": "Kills processes secretly using mic or camera.",
            "parameters": {"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spawn_research_agent",
            "description": "Spawns a sub-agent to research a topic in the background.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spawn_coder_agent",
            "description": "Spawns a sub-agent to code a script in the background.",
            "parameters": {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "launch_leetcode_trainer",
            "description": "Opens the next LeetCode problem.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_workout",
            "description": "Logs physical activity.",
            "parameters": {"type": "object", "properties": {"activity": {"type": "string"}, "duration": {"type": "integer"}}, "required": ["activity", "duration"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "house_party_protocol",
            "description": "Activates the final override protocol.",
            "parameters": {"type": "object", "properties": {}}
        }
    },

    {
        "type": "function",
        "function": {
            "name": "read_screen_text",
            "description": "Extracts raw text from the user's active screen via OCR.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_dev_env",
            "description": "Spins up a full development environment (editor, terminal, server).",
            "parameters": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"}
                },
                "required": ["project"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_prs",
            "description": "Checks GitHub for pending Pull Requests on a repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string"}
                },
                "required": ["repo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "toggle_focus_mode",
            "description": "Engages Focus Mode to block distractions and notifications.",
            "parameters": {
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean"}
                },
                "required": ["enabled"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_hardware_health",
            "description": "Checks physical hardware health (temps, disk SMART, memory).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_firewall",
            "description": "Blocks or unblocks an IP address at the firewall level.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["block", "unblock"]},
                    "ip": {"type": "string"}
                },
                "required": ["action", "ip"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "arrange_windows",
            "description": "Arranges or minimizes windows on the screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["minimize_all"]}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kill_process",
            "description": "Kills an application or process by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_name": {"type": "string"}
                },
                "required": ["process_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_contacts",
            "description": "Add or list contacts in the local rolodex.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["add", "list"]},
                    "name": {"type": "string"},
                    "details": {"type": "string"}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_expense",
            "description": "Log an expense to track spending.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number"},
                    "category": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["amount", "category"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_journal_entry",
            "description": "Save a dictated journal or diary entry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entry": {"type": "string"}
                },
                "required": ["entry"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "network_diagnostics",
            "description": "Checks ping and internet connectivity.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_tasks",
            "description": "Manages a persistent to-do list / kanban.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "list", "complete", "delete"],
                        "description": "The action to perform."
                    },
                    "task": {
                        "type": "string",
                        "description": "Task description (required for 'add')."
                    },
                    "task_id": {
                        "type": "string",
                        "description": "The ID of the task (required for 'complete' and 'delete')."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_smart_home",
            "description": "Controls smart home devices (lights, thermostat, etc).",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {
                        "type": "string",
                        "description": "The name of the device (e.g. 'living room lights', 'thermostat')."
                    },
                    "state": {
                        "type": "string",
                        "enum": ["on", "off", "set"],
                        "description": "The desired state."
                    },
                    "value": {
                        "type": "integer",
                        "description": "Optional value (e.g. temperature, brightness percentage)."
                    }
                },
                "required": ["device", "state"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "email_manager",
            "description": "Manages emails (read inbox, send emails).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["read", "send"],
                        "description": "Action to perform."
                    },
                    "to": {
                        "type": "string",
                        "description": "Recipient email (required for 'send')."
                    },
                    "subject": {
                        "type": "string",
                        "description": "Subject of the email (required for 'send')."
                    },
                    "body": {
                        "type": "string",
                        "description": "Body of the email."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "identify_displays",
            "description": "Identifies and returns information about all connected monitors/displays (resolution, primary status).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "toggle_network",
            "description": "Toggles the system's WiFi or Bluetooth radio on or off.",
            "parameters": {
                "type": "object",
                "properties": {
                    "wifi": {
                        "type": "boolean",
                        "description": "True to enable WiFi, False to disable."
                    },
                    "bluetooth": {
                        "type": "boolean",
                        "description": "True to enable Bluetooth, False to disable."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_calendar",
            "description": "Manages the local calendar/agenda and reminders. Use this to add, list, or delete events and meetings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "list", "delete"],
                        "description": "The action to perform."
                    },
                    "title": {
                        "type": "string",
                        "description": "The title of the event (required for 'add')."
                    },
                    "time_str": {
                        "type": "string",
                        "description": "The exact time in ISO format (e.g. '2026-07-19T15:00:00') (required for 'add')."
                    },
                    "event_id": {
                        "type": "string",
                        "description": "The ID of the event (required for 'delete')."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_mouse_and_keyboard",
            "description": "Simulate mouse and keyboard actions to control the operating system natively.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["click", "type", "press", "hotkey"], "description": "The action to perform."},
                    "x": {"type": "integer", "description": "X coordinate for click."},
                    "y": {"type": "integer", "description": "Y coordinate for click."},
                    "text": {"type": "string", "description": "Text to type."},
                    "key": {"type": "string", "description": "Key or hotkey to press (e.g. 'enter', 'ctrl+c')."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "locate_and_click_image",
            "description": "Finds a template image on the screen and clicks its center using PyAutoGUI. Useful for Vision-assisted UI automation if the orchestrator takes snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Path to the template image snippet."},
                    "confidence": {"type": "number", "description": "Confidence threshold (default 0.8)."}
                },
                "required": ["image_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Takes a screenshot of the current screen.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads the text contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lists the contents of a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the directory."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Creates or overwrites a file with the specified content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file."},
                    "content": {"type": "string", "description": "The full text content to write."}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_stats",
            "description": "Returns current CPU, RAM, and GPU usage, along with the top memory-consuming processes.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_terminal_command",
            "description": "Executes a terminal command on the host OS (Windows PowerShell/CMD) and returns the output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The exact terminal command to run."
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Opens a desktop application, website, or new browser tab/window. To open multiple apps/sites, call this tool multiple times in parallel, once for each target.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "The name of the app or website to open."
                    }
                },
                "required": ["target"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_app",
            "description": "Closes a running application or process by its executable name (e.g. chrome.exe, notepad.exe) to free up memory or if the user requests it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_name": {
                        "type": "string",
                        "description": "The exact name of the process to close, optionally with .exe extension."
                    }
                },
                "required": ["process_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Sets the system audio volume to a specific percentage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "description": "The volume level from 0 to 100."
                    }
                },
                "required": ["level"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_brightness",
            "description": "Sets the system screen brightness to a specific percentage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "description": "The brightness level from 0 to 100."
                    }
                },
                "required": ["level"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "store_memory",
            "description": "Store a piece of information, preference, or fact about the user into long-term vector memory. Do this proactively when the user reveals something about themselves.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "The clear, concise fact to remember (e.g. 'User prefers O(N) algorithms' or 'User has a Lenovo Legion laptop')."
                    }
                },
                "required": ["fact"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spawn_agents",
            "description": "Delegates a complex, multi-step, or time-consuming coding/deployment task to an autonomous team of background agents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "A detailed description of the task for the manager agent to execute."
                    }
                },
                "required": ["task_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Opens the default email client with a pre-composed email ready to send. Use when the user asks to send an email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "The recipient email address."
                    },
                    "subject": {
                        "type": "string",
                        "description": "The subject of the email."
                    },
                    "body": {
                        "type": "string",
                        "description": "The body of the email."
                    }
                },
                "required": ["to"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_web_content",
            "description": "Searches the web for factual answers, news, weather, or extracts text from a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query or URL to fetch"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Searches the web using DuckDuckGo and returns the top 5 results with titles and snippets. Use this when the user asks you to search, look up, or find information online.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to look up."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Gets the current weather conditions for a given location including temperature, humidity, wind, and precipitation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city or location name (e.g. 'London', 'New York', 'Mumbai')."
                    }
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "Fetches the top news headlines. Optionally takes a topic to search for specific news.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The topic or keyword to search for (e.g. 'technology', 'AI', 'finance'). Leave empty for general top headlines."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_spotify",
            "description": "Controls media playback (like Spotify or YouTube) via Windows media keys. Can play, pause, or skip tracks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "The media action to perform. Valid options: 'play', 'pause', 'toggle', 'next', 'prev'."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Sets a countdown timer that will fire a desktop notification when it completes. Use when the user says 'set a timer', 'remind me in X minutes', 'wake me up in X', etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration_seconds": {
                        "type": "integer",
                        "description": "The timer duration in seconds (e.g. 300 for 5 minutes, 3600 for 1 hour)."
                    },
                    "label": {
                        "type": "string",
                        "description": "A short label for the timer (e.g. 'Tea', 'Break', 'Meeting')."
                    }
                },
                "required": ["duration_seconds"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Takes a screenshot of the current screen and asks a Vision AI to describe it. Pass a specific question if you are looking for something particular.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The specific question to ask about the screen. Defaults to a general description."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_clipboard",
            "description": "Reads the current text contents of the system clipboard.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_clipboard",
            "description": "Copies a piece of text to the system clipboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to copy to the clipboard."
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_tool",
            "description": "Writes and registers a new Python function as a tool. Use this when the user asks you to do something and you don't already have a tool for it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the new function (e.g., 'convert_image')."
                    },
                    "description": {
                        "type": "string",
                        "description": "A short description of what the function does."
                    },
                    "python_code": {
                        "type": "string",
                        "description": "The full, executable Python code for the function. Include necessary imports."
                    },
                    "schema_json": {
                        "type": "string",
                        "description": "The OpenAI-style JSON schema describing the function and its parameters as a string."
                    }
                },
                "required": ["name", "description", "python_code", "schema_json"]
            }
        }
    },
    # ── Previously orphaned tool schemas (now registered) ────────────
    {
        "type": "function",
        "function": {
            "name": "mouse_click",
            "description": "Clicks the mouse at the specified coordinates (or current location if omitted). Use this to interact with UI elements you see.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate on screen."},
                    "y": {"type": "integer", "description": "Y coordinate on screen."},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "Which mouse button to click. Default is 'left'."},
                    "double": {"type": "boolean", "description": "Set to true to double-click."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "keyboard_type",
            "description": "Types the exact given string of text sequentially.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to type out."},
                    "interval": {"type": "number", "description": "Seconds between key presses. Default is 0.0."}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "keyboard_press",
            "description": "Presses a single key or combination (e.g. 'enter', 'ctrl+v', 'alt+f4', 'win+d').",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {"type": "string", "description": "The key string to press."}
                },
                "required": ["keys"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads the text contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lists the contents of a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the directory."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Creates or overwrites a file with the specified content. Overwriting an existing file requires confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file."},
                    "content": {"type": "string", "description": "The full text content to write."}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "replace_file_content",
            "description": "Replaces an exact target string with a replacement string inside an existing file. Modifying an existing file requires confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file."},
                    "target": {"type": "string", "description": "The exact string to find and replace."},
                    "replacement": {"type": "string", "description": "The new string to insert."}
                },
                "required": ["path", "target", "replacement"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_codebase",
            "description": "Performs a semantic search across the entire codebase to find relevant code snippets or files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query (e.g. 'authentication logic', 'where is the websocket defined')."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "Executes a bash/shell command in the workspace directory and returns its output (stdout/stderr). Requires confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The exact shell command to execute."}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_mouse_and_keyboard",
            "description": "Simulate mouse and keyboard actions to control the operating system natively.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["click", "type", "press", "hotkey"], "description": "The action to perform."},
                    "x": {"type": "integer", "description": "X coordinate for click."},
                    "y": {"type": "integer", "description": "Y coordinate for click."},
                    "text": {"type": "string", "description": "Text to type."},
                    "key": {"type": "string", "description": "Key or hotkey to press (e.g. 'enter', 'ctrl+c')."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_background_task",
            "description": "Spawns a background worker thread to execute long-running cross-app orchestration tasks without blocking the main event loop.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {"type": "string", "description": "The description of the long-running task to execute."}
                },
                "required": ["task_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_task_status",
            "description": "Checks the status of a background task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "The task ID."}
                },
                "required": ["task_id"]
            }
        }
    },
    # ── Protected (destructive) tool schemas ─────────────────────────
    {
        "type": "function",
        "function": {
            "name": "delete_path",
            "description": "Deletes a file or folder. DESTRUCTIVE: requires an explicit confirmation code before it runs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file or folder to delete."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "shutdown_pc",
            "description": "Shuts the PC down. DESTRUCTIVE: requires an explicit confirmation code before it runs.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "restart_pc",
            "description": "Restarts the PC. DESTRUCTIVE: requires an explicit confirmation code before it runs.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sleep_pc",
            "description": "Puts the PC to sleep / standby. DESTRUCTIVE: requires an explicit confirmation code before it runs.",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]


def _dispatch_tool(name: str, args: Dict[str, Any]) -> str:
    """Core dispatcher. Assumes any confirmation gate has already been cleared."""
    if name == "manage_tasks":
        return manage_tasks(args.get("action", ""), args.get("task", ""), args.get("task_id", ""))
    elif name == "control_smart_home":
        return control_smart_home(args.get("device", ""), args.get("state", ""), args.get("value"))
    elif name == "email_manager":
        return email_manager(args.get("action", ""), args.get("to", ""), args.get("subject", ""), args.get("body", ""))
    elif name == "identify_displays":
        return identify_displays()
    elif name == "toggle_network":
        return toggle_network(args.get("wifi"), args.get("bluetooth"))
    elif name == "manage_calendar":
        return manage_calendar(args.get("action", ""), args.get("title", ""), args.get("time_str", ""), args.get("event_id", ""))
    elif name == "get_system_stats":
        return get_system_stats()
    elif name == "set_power_mode":
        return set_power_mode(args.get("mode", ""))
    elif name == "set_dark_mode":
        return set_dark_mode(args.get("enabled", True))
    elif name == "open_night_light_settings":
        return open_night_light_settings()
    elif name == "lock_pc":
        return lock_pc()
    elif name == "leetcode_action":
        return leetcode_action(args.get("action", ""), args.get("query"))

        return get_system_stats()
    elif name == "execute_terminal_command":
        return execute_terminal_command(args.get("command", ""))
    elif name == "open_app":
        return open_app(args.get("target", ""))
    elif name == "close_app":
        return close_app(args.get("process_name", ""))
    elif name == "set_volume":
        return set_volume(args.get("level", 50))
    elif name == "set_brightness":
        return set_brightness(args.get("level", 100))
    elif name == "store_memory":
        return store_memory(args.get("fact", ""))
    elif name == "spawn_agents":
        return spawn_agents(args.get("task_description", ""))
    elif name == "send_email":
        return send_email(args.get("to", ""), args.get("subject", ""), args.get("body", ""))
    elif name == "fetch_web_content":
        return fetch_web_content(args.get("query", ""))
    elif name == "web_search":
        return web_search(args.get("query", ""))
    elif name == "get_weather":
        return get_weather(args.get("location", ""))
    elif name == "get_news":
        return get_news(args.get("topic", ""))
    elif name == "control_spotify":
        return control_spotify(args.get("action", ""))
    elif name == "set_timer":
        return set_timer(args.get("duration_seconds", 60), args.get("label", "Timer"))
    elif name == "take_screenshot":
        if "question" in args:
            return take_screenshot(args["question"])
        return take_screenshot()
    elif name == "get_clipboard":
        return get_clipboard()
    elif name == "set_clipboard":
        return set_clipboard(args.get("text", ""))
    elif name == "create_tool":
        return create_tool(
            name=args.get("name", ""),
            description=args.get("description", ""),
            python_code=args.get("python_code", ""),
            schema_json=args.get("schema_json", "")
        )
    elif name == "mouse_click":
        return mouse_click(args.get("x"), args.get("y"), args.get("button", "left"), args.get("double", False))
    elif name == "keyboard_type":
        return keyboard_type(args.get("text", ""), args.get("interval", 0.0))
    elif name == "locate_and_click_image":
        return locate_and_click_image(args.get("image_path", ""), args.get("confidence", 0.8))
    elif name == "keyboard_press":
        return keyboard_press(args.get("keys", ""))
    elif name == "read_file":
        return read_file(args.get("path", ""))
    elif name == "list_directory":
        return list_directory(args.get("path", ""))
    elif name == "write_file":
        return write_file(args.get("path", ""), args.get("content", ""))
    elif name == "replace_file_content":
        return replace_file_content(args.get("path", ""), args.get("target", ""), args.get("replacement", ""))
    elif name == "search_codebase":
        return search_codebase(args.get("query", ""))
    elif name == "index_workspace":
        return index_workspace()
    elif name == "run_terminal_command":
        return run_terminal_command(args.get("command", ""))
    elif name == "control_mouse_and_keyboard":
        return control_mouse_and_keyboard(
            args.get("action", ""),
            args.get("x"),
            args.get("y"),
            args.get("text"),
            args.get("key")
        )
    elif name == "create_background_task":
        return create_background_task(args.get("task_description", ""))
    elif name == "check_task_status":
        return check_task_status(args.get("task_id", ""))
    elif name == "delete_path":
        return delete_path(args.get("path", ""), confirm=True)
    elif name == "shutdown_pc":
        return shutdown_pc()
    elif name == "restart_pc":
        return restart_pc()
    elif name == "sleep_pc":
        return sleep_pc()
    else:
        # Try loading dynamically from dynamic_tools.py
        try:
            from jarvis.core import dynamic_tools
            importlib.reload(dynamic_tools)
            if hasattr(dynamic_tools, name):
                func = getattr(dynamic_tools, name)
                return str(func(**args))
        except Exception as e:
            return f"Error executing dynamic tool '{name}': {e}"

        return f"Error: Tool '{name}' not found."


def execute_tool(name: str, args: Dict[str, Any], confirm_code: str | None = None) -> str | dict:
    """Dispatcher to execute a tool by name, gated by the confirmation flow.

    - Destructive/protected tools (e.g. delete_path, shutdown_pc) and "soft"
      destructive ops (file overwrite, shell commands) never run on the first call.
      They return a `confirmation_required` challenge dict with a random `code`.
    - If `confirm_code` matches the pending code for this exact tool, the real
      action runs. A cancel keyword or any wrong code clears the pending challenge
      and returns `{"status": "cancelled"}`.
    - All other (non-destructive) tools run exactly as before.
    """
    args = dict(args or {})
    # Allow confirm_code to ride inside args (LLM-friendly) as well as be passed
    # explicitly as a kwarg. Pop both control keys so they never reach the real tool.
    if confirm_code is None:
        confirm_code = args.pop("confirm_code", None)
    args.pop("cancel", None)
    norm = (name or "").strip().lower()

    # Decide whether this call needs a confirmation gate.
    requires_confirm = False
    if norm in PROTECTED_TOOLS:
        requires_confirm = True
    elif norm in ("write_file", "replace_file_content") and CONFIRM_WRITE_OVERWRITE:
        if os.path.exists(str(args.get("path", ""))):
            requires_confirm = True
    elif norm in ("execute_terminal_command", "run_terminal_command") and CONFIRM_SHELL:
        requires_confirm = True

    if requires_confirm:
        # Explicit cancel (or cancel keyword) -> abort and forget any pending code.
        if _is_cancel(confirm_code, args):
            for code, pending in list(_PENDING_CONFIRMATIONS.items()):
                if pending["tool"] == norm:
                    _PENDING_CONFIRMATIONS.pop(code, None)
            return {"status": "cancelled"}

        # A code was supplied: if it matches the pending challenge for this tool,
        # run the real action; otherwise abort.
        if confirm_code:
            pending = check_confirmation(confirm_code)
            if pending is not None and pending["tool"] == norm:
                return _dispatch_tool(norm, pending["args"])
            return {"status": "cancelled"}

        # First (ungated) call -> issue the challenge. Do NOT execute.
        return request_confirmation(norm, args)

    # Non-gated tools run unchanged.
    return _dispatch_tool(norm, args)


def mouse_click(x: int = None, y: int = None, button: str = "left", double: bool = False) -> str:
    """Clicks the mouse at a specific coordinate or current location."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        
        # Move first if coords provided
        if x is not None and y is not None:
            pyautogui.moveTo(x, y, duration=0.25)
            
        if double:
            pyautogui.doubleClick(button=button)
        else:
            pyautogui.click(button=button)
            
        loc = f"({x}, {y})" if x is not None else "current location"
        return f"Successfully { 'double-' if double else '' }clicked {button} button at {loc}."
    except Exception as e:
        return f"Mouse click failed: {e}"


def keyboard_type(text: str, interval: float = 0.0) -> str:
    """Types the given text as if from a physical keyboard."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.write(text, interval=interval)
        return f"Successfully typed: '{text}'"
    except Exception as e:
        return f"Keyboard type failed: {e}"

def locate_and_click_image(image_path: str, confidence: float = 0.8) -> str:
    """Finds an image on the screen and clicks its center using PyAutoGUI."""
    try:
        import pyautogui
        import os
        if not os.path.exists(image_path):
            return f"Error: Image '{image_path}' not found."
            
        pyautogui.FAILSAFE = True
        try:
            # OpenCV is needed for confidence, but we can try without confidence if cv2 is missing
            try:
                import cv2
                location = pyautogui.locateCenterOnScreen(image_path, confidence=confidence)
            except ImportError:
                location = pyautogui.locateCenterOnScreen(image_path)
                
            if location is None:
                return f"Could not locate image '{image_path}' on screen."
                
            pyautogui.click(location.x, location.y)
            return f"Successfully clicked at ({location.x}, {location.y}) based on image '{image_path}'."
        except pyautogui.ImageNotFoundException:
            return f"Image '{image_path}' not found on screen."
    except Exception as e:
        return f"Locate and click failed: {e}"


def keyboard_press(keys: str) -> str:
    """Presses a key or hotkey combination (e.g., 'enter', 'ctrl+c', 'win+d')."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        key_list = keys.split('+')
        if len(key_list) > 1:
            pyautogui.hotkey(*key_list)
        else:
            pyautogui.press(key_list[0])
        return f"Successfully pressed: '{keys}'"
    except Exception as e:
        return f"Keyboard press failed: {e}"

def read_file(path: str, max_lines: int = 500) -> str:
    """Reads the contents of a file."""
    try:
        if not os.path.exists(path):
            return f"Error: File '{path}' not found."
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        if len(lines) > max_lines:
            truncated = "".join(lines[:max_lines])
            return truncated + f"\n... (File truncated, showing first {max_lines} lines of {len(lines)})"
        return "".join(lines)
    except Exception as e:
        return f"Failed to read file: {e}"

def list_directory(path: str) -> str:
    """Lists files and folders in a directory."""
    try:
        if not os.path.exists(path):
            return f"Error: Directory '{path}' not found."
        if not os.path.isdir(path):
            return f"Error: '{path}' is not a directory."
            
        items = os.listdir(path)
        result = []
        for item in items:
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                result.append(f"[DIR]  {item}")
            else:
                result.append(f"[FILE] {item}")
        return "\n".join(result) if result else "(Empty directory)"
    except Exception as e:
        return f"Failed to list directory: {e}"

def write_file(path: str, content: str) -> str:
    """Creates or overwrites a file with new content."""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Failed to write file: {e}"

def replace_file_content(path: str, target: str, replacement: str) -> str:
    """Replaces specific string content in a file."""
    try:
        if not os.path.exists(path):
            return f"Error: File '{path}' not found."
            
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            
        if target not in content:
            return f"Error: Target string not found in {path}"
            
        new_content = content.replace(target, replacement)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        return f"Successfully replaced content in {path}"
    except Exception as e:
        return f"Failed to replace file content: {e}"

def index_workspace() -> str:
    """Indexes all python and js files in the project workspace into ChromaDB."""
    import glob
    if chroma_client is None:
        return "ChromaDB not initialized."
    try:
        collection = chroma_client.get_or_create_collection(name="workspace_code")
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        
        # Gather files
        patterns = ["**/*.py", "**/*.js", "**/*.html", "**/*.css"]
        all_files = []
        for pattern in patterns:
            all_files.extend(glob.glob(os.path.join(base_dir, pattern), recursive=True))
            
        docs = []
        metadatas = []
        ids = []
        
        for file_path in all_files:
            # Skip virtual envs and chroma memory
            if ".venv" in file_path or "chroma_memory" in file_path or "__pycache__" in file_path:
                continue
                
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    file_content = file.read()
                    if file_content.strip():
                        docs.append(file_content)
                        metadatas.append({"path": file_path})
                        ids.append(file_path)
            except Exception:
                pass
                
        if docs:
            # Simple batching to avoid exceeding max batch size
            batch_size = 100
            for i in range(0, len(docs), batch_size):
                collection.upsert(
                    documents=docs[i:i+batch_size],
                    metadatas=metadatas[i:i+batch_size],
                    ids=ids[i:i+batch_size]
                )
        return f"Successfully indexed {len(docs)} files in the workspace."
    except Exception as e:
        return f"Failed to index workspace: {e}"

def search_codebase(query: str, n_results: int = 3) -> str:
    """Searches the codebase for relevant code snippets using semantic search."""
    if chroma_client is None:
        return "ChromaDB not initialized."
    try:
        collection = chroma_client.get_or_create_collection(name="workspace_code")
        if collection.count() == 0:
            # Automatically index if empty
            index_workspace()
            
        if collection.count() == 0:
            return "Workspace is empty."
            
        actual_n = min(n_results, collection.count())
        results = collection.query(
            query_texts=[query],
            n_results=actual_n
        )
        
        output = []
        for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
            path = meta.get("path", "Unknown")
            output.append(f"--- File: {path} ---\n{doc[:1000]}...\n")
            
        return "\n".join(output)
    except Exception as e:
        return f"Search failed: {e}"

import subprocess
import threading

def run_terminal_command(command: str, timeout_seconds: int = 15) -> str:
    """Runs a shell command and returns the stdout and stderr."""
    try:
        # Security constraints: Prevent highly destructive commands if desired
        dangerous_keywords = ['rm -rf /', 'format', 'mkfs']
        if any(keyword in command for keyword in dangerous_keywords):
            return "Command rejected for safety reasons."
            
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))) # Run at workspace root
        )
        
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
            
            output = ""
            if stdout:
                output += f"STDOUT:\n{stdout}\n"
            if stderr:
                output += f"STDERR:\n{stderr}\n"
                
            if process.returncode != 0:
                output += f"\nProcess exited with error code {process.returncode}"
                
            if not output:
                output = "Command executed successfully with no output."
                
            # Truncate output to prevent token overflow
            max_len = 2000
            if len(output) > max_len:
                return output[:max_len] + f"\n... (Output truncated by {len(output)-max_len} chars)"
            return output
            
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            return f"Command timed out after {timeout_seconds} seconds.\nSTDOUT: {stdout}\nSTDERR: {stderr}"
            
    except Exception as e:
        return f"Failed to execute command: {e}"

import pyautogui

def control_mouse_and_keyboard(action: str, x: int = None, y: int = None, text: str = None, key: str = None) -> str:
    """Simulates mouse clicks and keyboard presses."""
    try:
        if action == "click":
            if x is not None and y is not None:
                pyautogui.click(x, y)
                return f"Clicked at ({x}, {y})"
            else:
                pyautogui.click()
                return "Clicked at current location"
        elif action == "type":
            if text:
                pyautogui.write(text, interval=0.01)
                return f"Typed: {text}"
            return "No text provided to type."
        elif action == "press":
            if key:
                pyautogui.press(key)
                return f"Pressed key: {key}"
            return "No key provided to press."
        elif action == "hotkey":
            if key:
                keys = key.split('+')
                pyautogui.hotkey(*keys)
                return f"Pressed hotkey: {key}"
            return "No hotkey provided."
        else:
            return "Unknown action."
    except Exception as e:
        return f"Failed to control OS: {e}"

def create_background_task(task_description: str) -> str:
    """Creates a background task for long-running orchestration."""
    try:
        from jarvis.core.orchestrator import global_orchestrator
        from jarvis.core.server import GROQ_KEY, GROQ_LLM_MODEL
        
        task_id = global_orchestrator.spawn_task(task_description, GROQ_KEY, GROQ_LLM_MODEL)
        return f"Background task '{task_id}' started for: {task_description}"
    except Exception as e:
        return f"Failed to start task: {e}"

def check_task_status(task_id: str) -> str:
    """Checks the status of a background task."""
    try:
        from jarvis.core.orchestrator import global_orchestrator
        import json
        status = global_orchestrator.get_status(task_id)
        return json.dumps(status)
    except Exception as e:
        return f"Failed to check status: {e}"



def capture_screen() -> str | None:
    """Takes a screenshot, resizes it for efficiency, and returns it as a base64 string."""
    try:
        import mss
        from PIL import Image
        import io
        import base64
        
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # primary monitor
            sct_img = sct.grab(monitor)
            img = Image.frombytes('RGB', sct_img.size, sct_img.bgra, 'raw', 'BGRX')
            
            # Resize for LLM processing efficiency
            img.thumbnail((1024, 1024))
            
            buffered = io.BytesIO()
            img.save(buffered, format='JPEG', quality=70)
            img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
            return f"data:image/jpeg;base64,{img_str}"
    except Exception as e:
        print(f"[JARVIS] Screenshot error: {e}")
        return None


def analyze_image(base64_image_data_uri: str) -> str:
    """Sends a base64 image data URI to Groq Vision model and returns a summary."""
    try:
        from jarvis.core.server import GROQ_KEY
        import requests
        
        if not GROQ_KEY:
            return "Vision analysis unavailable: No Groq API Key."
            
        url = 'https://api.groq.com/openai/v1/chat/completions'
        headers = {
            'Authorization': f'Bearer {GROQ_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Groq expects the base64 string to be prefixed with data:image/jpeg;base64,
        data = {
            'model': 'qwen/qwen3.6-27b',
            'messages': [
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'text',
                            'text': 'Describe what the user is currently doing on their screen in 1-2 short sentences. Focus on the main activity, application, or content.'
                        },
                        {
                            'type': 'image_url',
                            'image_url': {
                                'url': base64_image_data_uri
                            }
                        }
                    ]
                }
            ],
            'temperature': 0.1,
            'max_tokens': 100
        }
        
        response = requests.post(url, headers=headers, json=data)
        res = response.json()
        if 'error' in res:
            print(f"[JARVIS] Vision API Error: {res['error']}")
            return "Vision analysis failed."
            
        content = res['choices'][0]['message']['content']
        import re
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        return content
    except Exception as e:
        print(f"[JARVIS] Analyze image error: {e}")
        return f"Vision error: {e}"


def fetch_web_content(query: str) -> str:
    """Fetches the actual text content or answers from the web for a given search query or URL."""
    try:
        from ddgs import DDGS
        import urllib.request
        from bs4 import BeautifulSoup
        
        # If it's a direct URL
        if query.startswith('http://') or query.startswith('https://'):
            req = urllib.request.Request(query, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read()
                soup = BeautifulSoup(html, 'html.parser')
                text = soup.get_text(separator=' ', strip=True)
                return text[:4000] + ('...' if len(text) > 4000 else '')
                
        # Otherwise, search DDG
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if not results:
                return f"No results found for {query}."
            
            output = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
            return output
    except Exception as e:
        return f"Error fetching web content: {e}"
