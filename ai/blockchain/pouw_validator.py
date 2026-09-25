import hashlib
import json
import time
import math
import requests
import os

class PoUWValidator:
    """
    Proof of Useful Work (PoUW) Validator.
    Instead of hashing empty blocks, we validate the computational work done during AI inference/agent tasks.
    """
    
    BASE_REWARD_PER_TOKEN = 0.0001
    DIFFICULTY_MULTIPLIER = 1.0

    @classmethod
    def calculate_reward(cls, tokens_generated: int, latency_ms: float, vram_mb: float, is_tool_call: bool) -> float:
        """
        Calculates the amount of ZYRA to reward based on the useful work performed.
        Heavier tasks (more tokens, using tools, utilizing more VRAM) yield higher rewards.
        """
        if tokens_generated <= 0:
            return 0.0
            
        # Base reward scales linearly with tokens generated
        base = tokens_generated * cls.BASE_REWARD_PER_TOKEN
        
        # Multiplier for tool usage (Agentic work is more valuable than passive chat)
        tool_multiplier = 1.5 if is_tool_call else 1.0
        
        # Hardware multiplier (Simulates higher rewards for offering more compute power)
        # Using log10 so it doesn't scale infinitely
        hw_multiplier = math.log10(max(10, vram_mb)) / math.log10(8192) if vram_mb > 0 else 1.0
        
        # Calculate final reward
        reward = base * tool_multiplier * hw_multiplier * cls.DIFFICULTY_MULTIPLIER
        
        # Cap reward per single inference task to prevent abuse
        return round(min(reward, 50.0), 6)

    @classmethod
    def generate_proof(cls, task_type: str, cid: str, tokens: int, metrics: dict, wallet_address: str) -> dict:
        """
        Generates a cryptographic proof of the work done.
        In a real P2P network, nodes would verify this proof against a model checkpoint.
        For local simulation, we sign the metrics with the system timestamp.
        """
        timestamp = time.time()
        
        # Check if tools were used (indicated by task_type or metrics)
        is_tool = task_type == 'AGENT_EXECUTION'
        
        vram_mb = metrics.get('vram_mb', 0.0)
        latency_ms = metrics.get('latency_ms', 0.0)
        
        reward = cls.calculate_reward(tokens, latency_ms, vram_mb, is_tool)
        
        proof_payload = {
            "task_type": task_type,
            "wallet": wallet_address,
            "cid": cid,
            "tokens": tokens,
            "metrics": metrics,
            "timestamp": timestamp,
            "reward": reward
        }
        
        # Create a verifiable hash of the payload
        payload_str = json.dumps(proof_payload, sort_keys=True)
        proof_hash = hashlib.sha256(payload_str.encode()).hexdigest()
        
        proof_payload["proof_hash"] = proof_hash
        
        return proof_payload

    @classmethod
    def evaluate_trajectory_with_llm(cls, trajectory_data: str, model_name: str = None, p2p_node=None) -> tuple[bool, str]:
        """
        Acts as the Local AI Smart Judge (Execution-Based). 
        Downloads the workspace ZIP from P2P, extracts it, and runs pytest to mathematically prove success.
        """
        import tempfile
        import os
        import subprocess
        import shutil
        import re
        import asyncio
        import zipfile
        import glob

        try:
            sandbox = tempfile.mkdtemp(prefix="zyra_judge_")
            zip_path = os.path.join(sandbox, "workspace.zip")
            
            # Download file from P2P (via WebSocket Relay)
            cid = trajectory_data  # In real P2P, trajectory_log field holds the CID
            if not p2p_node:
                return False, "P2P Node not available for downloading workspace."
                
            print(f"[\033[96mSmart Judge\033[0m] Requesting file {cid} from P2P Network (Relay)...")
            try:
                future = asyncio.run_coroutine_threadsafe(p2p_node.request_file(cid, zip_path), p2p_node.loop)
                future.result(timeout=120) # wait up to 2 minutes
            except Exception as e:
                return False, f"Failed to download workspace via P2P Relay: {e}"
                
            print(f"[\033[96mSmart Judge\033[0m] Extracting workspace...")
            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(sandbox)
            except zipfile.BadZipFile:
                return False, "Downloaded file is not a valid ZIP archive."
                
            # Read extracted files
            files_to_write = {}
            for file_path in glob.glob(os.path.join(sandbox, "**", "*"), recursive=True):
                if os.path.isfile(file_path) and not file_path.endswith(".zip"):
                    rel_path = os.path.relpath(file_path, sandbox)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            files_to_write[rel_path] = f.read()
                    except Exception:
                        pass # Ignore binary files
                        
            initial_prompt = "Validate if the code inside the workspace correctly fulfills the requirements of the task."
                        
            if not files_to_write:
                return False, "Workspace is empty. Invalid."
                
            try:
                # 3. Ask LLM to generate a test script based on the prompt
                judge_model = model_name or os.environ.get("JUDGE_MODEL", "qwen2.5-coder:7b")
                file_list = ", ".join(files_to_write.keys())
                
                # Build file context string
                file_context = ""
                for filename, content in files_to_write.items():
                    file_context += f"--- {filename} ---\n```python\n{content}\n```\n\n"

                test_prompt = f"""You are a strict Smart Judge (QA Engineer) for a blockchain network.
The user requested this task: "{initial_prompt}"
The miner created the following files to solve it:
{file_context}

Write a comprehensive `unittest` script (using Python's built-in unittest module) that imports the miner's code and tests if the task was completed correctly based on the user's prompt.
If the miner's code is just a script that prints something, use `capsys` or `subprocess` to capture and test its output.
Do NOT test things that require an internet connection.
Only output the Python code wrapped in ```python ... ```. Do not add explanations.
"""
                payload = {
                    "model": judge_model,
                    "prompt": test_prompt,
                    "stream": False,
                    "options": {"temperature": 0.0}
                }
                
                print(f"[\033[96mSmart Judge\033[0m] Generating TDD Unittest script for validation...")
                resp = requests.post("http://localhost:11434/api/generate", json=payload, timeout=60)
                if resp.status_code == 200:
                    test_code_raw = resp.json().get('response', '')
                    match = re.search(r'```python\n(.*?)\n```', test_code_raw, re.DOTALL)
                    test_code = match.group(1) if match else test_code_raw.replace('```python', '').replace('```', '')
                        
                    test_path = os.path.join(sandbox, "test_zyra_validation.py")
                    with open(test_path, 'w', encoding='utf-8') as f:
                        f.write(test_code)
                        
                    # 4. Execute the test using unittest inside Docker (Secure) or Fallback (Insecure)
                    print(f"[\033[96mSmart Judge\033[0m] Running Execution-Based Validation in {sandbox} ...")
                    try:
                        command = "python -m unittest test_zyra_validation.py"
                        docker_cmd = [
                            "docker", "run", "--rm", 
                            "--network", "none", 
                            "--memory", "512m", 
                            "--cpus", "0.5",
                            "-v", f"{sandbox}:/app", 
                            "-w", "/app", 
                            "python:3.10-slim", 
                            "sh", "-c", command
                        ]
                        
                        try:
                            subprocess.run(["docker", "--version"], capture_output=True, check=True)
                            use_docker = True
                        except (subprocess.CalledProcessError, FileNotFoundError):
                            use_docker = False
                            
                        if use_docker:
                            result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=60)
                        else:
                            print(f"\033[91m[WARNING]\033[0m Docker not found. Falling back to local INSECURE validation in {sandbox}")
                            result = subprocess.run(["python", "-m", "unittest", "test_zyra_validation.py"], cwd=sandbox, capture_output=True, text=True, timeout=30)
                        
                        if result.returncode == 0:
                            print(f"[\033[92mSmart Judge\033[0m] TDD Validation PASSED!")
                            return True, "Execution-based validation passed."
                        else:
                            print(f"[\033[91mSmart Judge\033[0m] TDD Validation FAILED.\n\033[90mUnittest Output:\n{result.stdout.strip()[:1000]}\n{result.stderr.strip()[:1000]}\033[0m")
                            return False, f"Unittest failed. Tests did not pass."
                            
                    except subprocess.TimeoutExpired:
                        return False, "Validation script timed out."
                    except FileNotFoundError:
                        return False, "Python/Docker not installed on validator node."
                else:
                    return False, "Failed to generate test script."
                    
            finally:
                shutil.rmtree(sandbox, ignore_errors=True)
                
        except Exception as e:
            return False, f"AI Judge Exception: {e}"
