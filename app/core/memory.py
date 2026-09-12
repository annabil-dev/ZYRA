import os
import json
import datetime

def get_memory_file_path() -> str:
    """Returns the path to the memories.json file in APPDATA."""
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    base_dir = os.path.join(appdata, "ZYRA AI")
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "memories.json")

def load_memories() -> list:
    """Loads all saved memories from the JSON file."""
    path = get_memory_file_path()
    if not os.path.exists(path):
        return []
        
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Failed to load memories: {e}")
        return []

def save_memory(fact: str) -> str:
    """Saves a new fact to the long-term memory file."""
    path = get_memory_file_path()
    memories = load_memories()
    
    # Check if already exists to avoid duplicates
    for mem in memories:
        if mem.get("fact") == fact:
            return "Memory already exists."
            
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    memories.append({
        "fact": fact,
        "timestamp": now
    })
    
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(memories, f, indent=4)
        return "Memory successfully saved."
    except Exception as e:
        return f"Error saving memory: {e}"

def get_memory_context_string() -> str:
    """Returns a formatted string of all memories to inject into the system prompt."""
    memories = load_memories()
    if not memories:
        return ""
        
    context = "Here is what you know about the user (Long-term Memory):\n"
    for mem in memories:
        context += f"- {mem['fact']} (Learned on {mem['timestamp']})\n"
        
    return context
