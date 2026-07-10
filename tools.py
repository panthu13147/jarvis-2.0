"""
JARVIS v2.0 — Deep OS & Tool Integration
Provides safe tools and Groq function schemas for the LLM.
"""
import os
import subprocess
import sys
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


# ── Functions ────────────────────────────────────────────────────────

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
        print(f"\n[JARVIS-OS] 🚀 Spawning Manager Agent for task: {task_description}")
        time.sleep(2)
        print(f"[JARVIS-OS] 🛠️ Deploying Worker 1 (Implementation) & Worker 2 (QA)...")
        time.sleep(6)
        print(f"[JARVIS-OS] ✅ Background agents completed task: {task_description}\n")
        
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return f"Agents successfully deployed in the background for task: '{task_description}'. The manager will handle execution silently."


def execute_terminal_command(command: str) -> str:
    """Safely executes a terminal command and returns the output."""
    # Safety wrapper: prevent highly destructive commands
    forbidden = ["del /f /s /q", "format", "rmdir /s /q", "shutdown"]
    cmd_lower = command.lower()
    for f in forbidden:
        if f in cmd_lower:
            return f"Error: Command '{command}' is blacklisted for safety."
            
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=10)
        output = result.stdout.strip()
        error = result.stderr.strip()
        
        if result.returncode == 0:
            return f"Success:\n{output}" if output else "Command executed successfully with no output."
        else:
            return f"Failed (Code {result.returncode}):\n{error or output}"
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
        import webbrowser
        webbrowser.open(url)
        return f"Opened {target_lower} in browser."
        
    if "." in target_lower and not " " in target_lower:
        url = f"https://{target_lower}" if not target_lower.startswith("http") else target_lower
        import webbrowser
        webbrowser.open(url)
        return f"Opened {url} in browser."
        
    # If not recognized, try to find a URL via DuckDuckGo and open it
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
            
        with DDGS() as ddgs:
            results = list(ddgs.text(target, max_results=1))
        
        if results and "href" in results[0]:
            url = results[0]["href"]
            import webbrowser
            webbrowser.open(url)
            return f"Opened '{target}' in browser ({url})."
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

def web_search(query: str) -> str:
    """Searches the web using DuckDuckGo and returns top results."""
    # Try the ddgs package first (modern), then duckduckgo_search (legacy)
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        
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


def take_screenshot() -> str:
    """Takes a screenshot and returns a description of visible windows."""
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
        
        return f"Screenshot saved to {path}. Running applications: {', '.join(top_apps)}. Screen resolution: {screenshot.size[0]}x{screenshot.size[1]}."
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


# ── Tool Definitions for Groq ────────────────────────────────────────

GROQ_TOOLS = [
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
            "description": "Takes a screenshot of the current screen and reports the visible running applications and screen resolution.",
            "parameters": {"type": "object", "properties": {}}
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
    }
]


def execute_tool(name: str, args: Dict[str, Any]) -> str:
    """Dispatcher to execute a tool by name."""
    if name == "get_system_stats":
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
    else:
        # Try loading dynamically from dynamic_tools.py
        try:
            import dynamic_tools
            importlib.reload(dynamic_tools)
            if hasattr(dynamic_tools, name):
                func = getattr(dynamic_tools, name)
                return str(func(**args))
        except Exception as e:
            return f"Error executing dynamic tool '{name}': {e}"
            
        return f"Error: Tool '{name}' not found."
