import re
import sys
import os

with open('jarvis/core/tools.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add tool functions
new_funcs = '''
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
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize") as key:
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
        return f"Unknown leetcode action: {action}"
    except Exception as e:
        return f"Leetcode action failed: {e}"
'''

# insert before PROTECTED_TOOLS
content = content.replace('PROTECTED_TOOLS = {', new_funcs + '\\nPROTECTED_TOOLS = {')

# 2. Add to GROQ_TOOLS schema
new_schemas = '''
    {
        "type": "function",
        "function": {
            "name": "set_power_mode",
            "description": "Changes the Windows power plan/mode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["power saver", "balanced", "high performance"]}
                },
                "required": ["mode"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_dark_mode",
            "description": "Enables or disables Windows dark mode.",
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
            "name": "open_night_light_settings",
            "description": "Opens the Windows settings page to toggle Night Light.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lock_pc",
            "description": "Locks the Windows workstation.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "leetcode_action",
            "description": "Manages NeetCode 150 progress. Use 'status' for stats, 'daily' for today's new problem, 'revision' for due spaced repetition, 'solved' to mark a problem solved by name, and 'open' to open a problem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["status", "daily", "revision", "solved", "open"]},
                    "query": {"type": "string", "description": "The problem name if action is 'solved' or 'open'"}
                },
                "required": ["action"]
            }
        }
    },
'''

# insert at the beginning of GROQ_TOOLS array
content = content.replace('GROQ_TOOLS = [\\n', 'GROQ_TOOLS = [\\n' + new_schemas)

# 3. Add to _dispatch_tool
dispatch_add = '''
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
'''

content = content.replace('if name == "get_system_stats":', 'if name == "get_system_stats":' + dispatch_add)

with open('jarvis/core/tools.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Injection successful.")
