import re
import os

with open('jarvis/core/server.py', 'r', encoding='utf-8') as f:
    content = f.read()

fast_intent_func = '''
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
        if re.search(rf"\\b{name}\\b", lowered):
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
        if re.search(rf"\\b{re.escape(name)}\\b", lowered):
            if action == "close":
                tools.close_app(target)
                return {"response": f"Closing {name}."}
            tools.open_app(target)
            return {"response": f"Opening {name}."}

    url_match = re.search(r"(https?://[^\\s]+)|([a-z0-9-]+\\.(?:com|org|net|io|dev|edu|gov|co)\\b)", lowered)
    if url_match and action in {"open", "search"}:
        url = url_match.group(0)
        if action == "search":
            return {"response": f"Searching the web for {url}.", "tool": "web_search", "args": {"query": url}}
        tools.open_app(url)
        return {"response": f"Opening {url}."}

    return None
'''

stream_generator_injection = '''
        fast_res = _fast_intent(text)
        if fast_res:
            import json
            yield f"data: {json.dumps({'chunk': fast_res['response']})}\\n\\n"
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
            yield f"data: {json.dumps({'done': True, 'model': 'fast_intent'})}\\n\\n"
            return
'''

content = content.replace('def command(payload: CommandRequest):', fast_intent_func + '\n@app.post("/api/command")\ndef command(payload: CommandRequest):')

# replace `@app.post("/api/command")` from where it originally was
content = content.replace('@app.post("/api/command")\n\n@app.post("/api/command")', '@app.post("/api/command")')

# also remove the original decorator that I accidentally duplicated (wait, I should be careful)
# Let's do it safer:
'''
@app.post("/api/command")
def command(payload: CommandRequest):
'''

content = content.replace(
    '@app.post("/api/command")\ndef command(payload: CommandRequest):',
    fast_intent_func + '\n@app.post("/api/command")\ndef command(payload: CommandRequest):'
)

# insert into stream_generator
content = content.replace(
    '        global total_tokens\n        if not GROQ_KEY:',
    '        global total_tokens\n' + stream_generator_injection + '\n        if not GROQ_KEY:'
)

with open('jarvis/core/server.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Injected fast intent")
