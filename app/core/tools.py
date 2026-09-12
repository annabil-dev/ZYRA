import os
import json
import psutil
import datetime
import subprocess

# Tool Schemas for OpenAI / Ollama compatible endpoint
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lists the contents of a given directory. Use this to explore the user's file system.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The absolute path of the directory to list."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file_content",
            "description": "Reads the text content of a given file. Use this to inspect code, notes, or configuration files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The absolute path of the file to read."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Gets the current system information like time, OS, and memory usage.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file_content",
            "description": "Writes or overwrites text content to a file. Requires user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The absolute path of the file to write to."
                    },
                    "content": {
                        "type": "string",
                        "description": "The text content to write into the file."
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Executes a command in the system terminal/shell. Requires user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The terminal command to execute."
                    },
                    "cwd": {
                        "type": "string",
                        "description": "The working directory to run the command in. Defaults to current directory if empty."
                    }
                },
                "required": ["command"]
            }
        }
    }
]

# Implementations
def list_directory(path: str) -> str:
    """Lists contents of a directory safely."""
    try:
        if not os.path.exists(path):
            return f"Error: Directory '{path}' does not exist."
        if not os.path.isdir(path):
            return f"Error: '{path}' is not a directory."
            
        items = os.listdir(path)
        
        result = []
        for item in items:
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                result.append(f"[DIR] {item}")
            else:
                try:
                    size = os.path.getsize(item_path)
                    result.append(f"[FILE] {item} ({size} bytes)")
                except Exception:
                    result.append(f"[FILE] {item} (unknown size)")
                    
        if not result:
            return f"Directory '{path}' is empty."
            
        return "Contents of " + path + ":\n" + "\n".join(result)
    except Exception as e:
        return f"Error reading directory: {str(e)}"

def read_file_content(path: str) -> str:
    """Reads a file securely with a size limit (e.g., max 1MB) to prevent blowing up the context window."""
    try:
        if not os.path.exists(path):
            return f"Error: File '{path}' does not exist."
        if not os.path.isfile(path):
            return f"Error: '{path}' is not a file."
            
        # 1MB limit
        if os.path.getsize(path) > 1024 * 1024:
            return f"Error: File is too large to read (>{1}MB). Try another file."
            
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return content
    except UnicodeDecodeError:
        return f"Error: File '{path}' is not a readable text file (likely binary)."
    except Exception as e:
        return f"Error reading file: {str(e)}"

def get_system_info() -> str:
    """Gets basic system context."""
    mem = psutil.virtual_memory()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    return json.dumps({
        "current_time": now,
        "os": os.name,
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": mem.percent,
        "memory_total_gb": round(mem.total / (1024**3), 2),
        "memory_available_gb": round(mem.available / (1024**3), 2)
    })

def write_file_content(path: str, content: str) -> str:
    """Writes text content to a file."""
    try:
        # Create directories if they don't exist
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to file '{path}'."
    except Exception as e:
        return f"Error writing file: {str(e)}"

def run_command(command: str, cwd: str = None) -> str:
    """Executes a terminal command and returns the output."""
    try:
        if not cwd or not os.path.exists(cwd):
            cwd = os.getcwd()
            
        # Run command with a timeout of 30 seconds to prevent hanging
        result = subprocess.run(
            command, 
            shell=True, 
            cwd=cwd,
            capture_output=True, 
            text=True,
            timeout=30
        )
        
        output = f"Command exited with code {result.returncode}.\n"
        if result.stdout:
            # Truncate stdout if it's too long (e.g. > 4000 chars)
            out_str = result.stdout
            if len(out_str) > 4000:
                out_str = out_str[:4000] + "\n...[STDOUT TRUNCATED]..."
            output += f"STDOUT:\n{out_str}\n"
        if result.stderr:
            err_str = result.stderr
            if len(err_str) > 4000:
                err_str = err_str[:4000] + "\n...[STDERR TRUNCATED]..."
            output += f"STDERR:\n{err_str}\n"
            
        return output.strip()
    except subprocess.TimeoutExpired:
        return f"Error: Command '{command}' timed out after 30 seconds."
    except Exception as e:
        return f"Error executing command: {str(e)}"

def execute_tool(tool_name: str, arguments: dict, security_callback=None) -> str:
    """Dispatcher to safely execute a tool and return the string response."""
    try:
        # DANGEROUS TOOLS - require security clearance
        if tool_name in ["write_file_content", "run_command"]:
            if security_callback:
                allowed = security_callback(tool_name, arguments)
                if not allowed:
                    return f"Error: The user denied permission to execute '{tool_name}'."
            else:
                # If no security callback provided, fail safe
                return f"Error: Security check failed. Cannot execute '{tool_name}'."
                
            if tool_name == "write_file_content":
                return write_file_content(arguments.get("path", ""), arguments.get("content", ""))
            elif tool_name == "run_command":
                return run_command(arguments.get("command", ""), arguments.get("cwd", None))
                
        # SAFE TOOLS
        elif tool_name == "list_directory":
            return list_directory(arguments.get("path", ""))
        elif tool_name == "read_file_content":
            return read_file_content(arguments.get("path", ""))
        elif tool_name == "get_system_info":
            return get_system_info()
        else:
            return f"Error: Unknown tool '{tool_name}'."
    except Exception as e:
        return f"Error executing tool '{tool_name}': {str(e)}"
