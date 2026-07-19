import threading
import uuid
import time
import json
import requests
import subprocess
import psutil
from datetime import datetime

class TaskOrchestrator:
    def __init__(self):
        self.tasks = {}

    def spawn_task(self, task_description: str, groq_key: str, groq_model: str) -> str:
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "status": "Starting",
            "description": task_description,
            "created_at": datetime.now().isoformat(),
            "logs": [],
            "result": None
        }

        thread = threading.Thread(target=self._run_task, args=(task_id, task_description, groq_key, groq_model), daemon=True)
        thread.start()
        
        return task_id

    def get_status(self, task_id: str) -> dict:
        return self.tasks.get(task_id, {"status": "Unknown task_id"})
        
    def _run_task(self, task_id: str, task_description: str, groq_key: str, groq_model: str):
        self.tasks[task_id]["status"] = "Running"
        self._log(task_id, f"Agent spawned for task: {task_description}")
        
        try:
            from jarvis.core.tools import GROQ_TOOLS
            
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a JARVIS background orchestrator agent. "
                        "Your goal is to execute the user's complex task autonomously. "
                        "You must use tools to execute the task. "
                        "When you are finished, output a JSON object: {\"done\": true, \"summary\": \"What you accomplished\"}. "
                        "Do not ask for user input. If you hit an error, try an alternative."
                    )
                },
                {"role": "user", "content": task_description}
            ]
            
            # Simple 10-step autonomous loop
            for step in range(10):
                self._log(task_id, f"Starting step {step+1}/10...")
                
                payload = {
                    "model": groq_model,
                    "messages": messages,
                    "temperature": 0.2,
                    "tools": GROQ_TOOLS,
                    "tool_choice": "auto"
                }
                
                max_retries = 3
                for attempt in range(max_retries):
                    resp = requests.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                        json=payload,
                        timeout=30
                    )
                    if resp.status_code == 429:
                        self._log(task_id, f"Rate limited. Waiting {5 * (attempt + 1)} seconds...")
                        time.sleep(5 * (attempt + 1))
                        continue
                    break
                
                if resp.status_code != 200:
                    self._log(task_id, f"API Error: {resp.text}")
                    break
                    
                data = resp.json()
                message_obj = data["choices"][0]["message"]
                
                if message_obj.get("content") is None:
                    message_obj["content"] = ""
                    
                messages.append(message_obj)
                
                # Check if done
                content = message_obj.get("content", "")
                if content:
                    try:
                        parsed = json.loads(content)
                        if parsed.get("done"):
                            self._log(task_id, f"Task complete: {parsed.get('summary')}")
                            self.tasks[task_id]["result"] = parsed.get("summary")
                            break
                    except json.JSONDecodeError:
                        pass
                
                # Execute tools
                if message_obj.get("tool_calls"):
                    for tool_call in message_obj["tool_calls"]:
                        func_name = tool_call["function"]["name"]
                        try:
                            func_args = json.loads(tool_call["function"]["arguments"])
                        except json.JSONDecodeError:
                            func_args = {}
                            
                        self._log(task_id, f"Executing tool {func_name}...")
                        from jarvis.core.tools import execute_tool
                        tool_result = execute_tool(func_name, func_args)
                        
                        messages.append({
                            "role": "tool",
                            "content": str(tool_result),
                            "tool_call_id": tool_call["id"]
                        })
                else:
                    # If no tools called and not done, force it to continue
                    messages.append({"role": "user", "content": "Please continue executing tools, or output {\"done\": true, \"summary\": \"...\"} if finished."})
            
            self.tasks[task_id]["status"] = "Completed"
            self._notify_user(task_description, "Completed successfully")
            
        except Exception as e:
            self.tasks[task_id]["status"] = f"Failed: {str(e)}"
            self._log(task_id, f"Task failed with exception: {e}")
            self._notify_user(task_description, "Failed")
            
    def _log(self, task_id: str, message: str):
        print(f"[Orchestrator|{task_id[:8]}] {message}")
        if task_id in self.tasks:
            self.tasks[task_id]["logs"].append(f"{datetime.now().time().isoformat()} - {message}")
            
    def _notify_user(self, task: str, status: str):
        try:
            from plyer import notification
            notification.notify(
                title=f"JARVIS Task {status}",
                message=task[:50] + "...",
                app_name="JARVIS",
                timeout=5
            )
        except Exception:
            pass

global_orchestrator = TaskOrchestrator()
