import os
import sys
import time
import json
import argparse
import subprocess
import re
import requests
from pathlib import Path

# Fix Windows console encoding for Emojis
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
# Suppress annoying HTTP request logs from requests and urllib3
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
from ai.inference.local_llm_client import LocalLLMGenerator
from ai.blockchain.wallet import ZyraWallet
from ai.blockchain.ledger import ZyraLedger
from ai.blockchain.pouw_validator import PoUWValidator
import dotenv

# Load .env from current directory first (for users running zyra in their project dir)
dotenv.load_dotenv(".env")
# Fallback to global user config
global_env_dir = Path.home() / ".zyra"
global_env_dir.mkdir(parents=True, exist_ok=True)
global_env_path = global_env_dir / ".env"
if global_env_path.exists():
    dotenv.load_dotenv(str(global_env_path))
# Fallback to package root
dotenv.load_dotenv(str(Path(__file__).resolve().parent.parent / '.env'))

BRIDGE_URL = os.environ.get("ZYRA_BRIDGE_URL", "http://127.0.0.1:5000") # Default to localhost instead of pinggy to prevent offline errors during development

def print_animated(text):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(0.01)
    print()

import threading
import sys
import time

def process_prompt(llm, prompt, history, wallet, ledger, model_name):
    print() # newline
    
    is_thinking = True
    def spinner():
        spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        i = 0
        while is_thinking:
            sys.stdout.write(f'\r\033[94mZYRA is thinking {spinner_chars[i]}\033[0m')
            sys.stdout.flush()
            time.sleep(0.1)
            i = (i + 1) % len(spinner_chars)
        sys.stdout.write('\r\033[K') # Clear line
        sys.stdout.flush()
        
    spinner_thread = threading.Thread(target=spinner)
    spinner_thread.daemon = True
    spinner_thread.start()
    
    start_time = time.time()
    total_tokens = 0
    final_text = ""
    is_tool_call = False
    
    def cli_security_callback(tool_name, arguments_dict):
        nonlocal is_thinking
        if is_thinking:
            is_thinking = False
            spinner_thread.join()
        print(f"\n\033[93m[AGENT ACTION]\033[0m Executing \033[96m{tool_name}\033[0m...\n")
        return True # Auto approve in CLI for developers
        
    try:
        # Stream the response
        for text, delta, metrics in llm.generate(
            prompt=prompt,
            history=history,
            max_tokens=4096,
            temperature=0.4,
            top_k=40,
            top_p=0.9,
            security_callback=cli_security_callback
        ):
            if is_thinking:
                is_thinking = False
                spinner_thread.join()
                
            if "tool_calls" in text:
                is_tool_call = True
            
            # Print delta
            sys.stdout.write(delta)
            sys.stdout.flush()
            total_tokens += 1
            final_text = text
            
        print("\n")
        
        # Append to history
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": final_text})
        
        # Prevent Context Overflow (Keep last 10 interactions / 20 messages)
        if len(history) > 20:
            history[:] = history[-20:]
            
    except (Exception, KeyboardInterrupt) as e:
        if is_thinking:
            is_thinking = False
            spinner_thread.join()
        print(f"\n\033[91m[INTERRUPTED]\033[0m {str(e)}")
        return
        
    end_time = time.time()
    latency_ms = (end_time - start_time) * 1000
    
    # --- PoUW MINING LOGIC ---
    print("\033[93m[PoUW Validator]\033[0m Submitting Proof of Useful Work...")
    
    import uuid
    
    trajectory_data = {
        "prompt": prompt,
        "response": final_text,
        "history": history,
        "wallet": wallet.address,
        "timestamp": time.time()
    }
    
    print("\033[94m[IPFS]\033[0m Requesting Tracker Server to pin payload to Pinata...")
    try:
        res = requests.post(f"{BRIDGE_URL}/api/ipfs/upload", json={"trajectory": trajectory_data}, timeout=30)
        res.raise_for_status()
        cid = res.json().get("cid")
    except Exception as e:
        print(f"\033[91m[IPFS ERROR]\033[0m Could not upload via Tracker Server: {e}")
        cid = None

    if not cid:
        cid = f"LOCAL_{uuid.uuid4().hex}"
        
    proof = PoUWValidator.generate_proof(
        task_type="AGENT_EXECUTION" if is_tool_call else "TEXT_GEN",
        cid=cid,
        tokens=total_tokens,
        metrics={"latency_ms": latency_ms, "vram_mb": 0.0},
        wallet_address=wallet.address
    )
    
    reward = proof.get('reward', 0.0)
    if reward > 0:
        ledger.add_pouw_reward(wallet.address, reward, proof)
        
        # Broadcast the PoUW trajectory to the P2P network
        global p2p_node
        if 'p2p_node' in globals():
            import uuid
            traj_payload = {
                "trajectory_hash": proof.get("proof_hash", str(uuid.uuid4().hex)),
                "cid": cid,
                "wallet": proof.get("wallet", "Z_UNKNOWN"),
                "reward": proof.get("reward", 0),
                "metrics": proof.get("metrics", {}),
                "timestamp": proof.get("timestamp", 0)
            }
            p2p_node.add_trajectory(traj_payload)
            print(f"\033[94m[P2P]\033[0m Broadcasted Trajectory to P2P network.")
            
        print(f"\033[92m[SUCCESS]\033[0m You earned \033[1m+{reward:.4f} ZYRA\033[0m for this terminal task!\n")
    else:
        print("\033[91m[REJECTED]\033[0m Task did not qualify for PoUW rewards.\n")


def run_automode(llm, initial_task: str, history: list, wallet: ZyraWallet, ledger: ZyraLedger, model_name: str, auto_yes: bool = False, planner_model: str = None, coder_model: str = None, task_id: str = None):
    # Auto-detect specialist models if not provided
    if not planner_model or not coder_model:
        try:
            import urllib.request, json
            req = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
            avail_models = [m['name'] for m in json.loads(req.read().decode('utf-8')).get('models', [])]
            if not planner_model:
                planner_model = next((m for m in avail_models if 'deepseek-r1' in m), model_name)
            if not coder_model:
                coder_model = next((m for m in avail_models if 'coder' in m or 'codellama' in m), model_name)
        except Exception:
            planner_model = planner_model or model_name
            coder_model = coder_model or model_name

    print(f"\n\033[95m[Multi-Agent Swarm]\033[0m Initializing ZYRA Swarm Intelligence...")
    print(f"\033[95m[Task]\033[0m \033[96m{initial_task}\033[0m")
    print(f"\033[90m[Models] Planner: {planner_model} | Coder: {coder_model}\033[0m\n")
    
    planner_history = []
    coder_history = []
    full_trajectory_log = []
    full_trajectory_log.append({"role": "user", "content": f"TASK: {initial_task}"})
    
    planner_sys = f"""You are the PLANNER AGENT (Mandor).
Task: {initial_task}
RULES:
1. Break down the task into technical steps. To save time, you MUST combine related simple actions (e.g., creating a directory and writing a file inside it) into a single <DELEGATE> instruction whenever possible. Do not over-complicate simple tasks.
2. Delegate to the CODER AGENT using exactly this format:
<DELEGATE>instruction for coder</DELEGATE>
3. Wait for the Coder to report completion before sending the next <DELEGATE>. DO NOT send multiple <DELEGATE> tags in a single message.
4. You CANNOT execute code. You only plan and delegate.
5. Trust the Coder if they report success. DO NOT ask the coder to execute the exact same task twice. Proceed to the next step or finish.
6. DO NOT output <ALL_DONE> until you have verified all steps are truly finished.
7. When the entire task is truly finished, output exactly:
<ALL_DONE>
8. If the system asks you to confirm completion, and you are 100% sure, reply exactly:
<CONFIRM_DONE>"""
    planner_history.append({"role": "user", "content": planner_sys})
    
    coder_sys = """You are the CODER AGENT running in a SECURE LINUX DOCKER SANDBOX (python:3.10-slim).
You will receive instructions from the PLANNER.
RULES:
1. You are on Linux. DO NOT use Windows/PowerShell commands. Use standard Linux commands (e.g., `ls`, `cat`, `python`).
2. CRITICAL RULE: Your environment is ephemeral and has NO internet access (network=none). Do NOT try to `pip install` packages or download files. Use standard libraries.
3. You are executing in the `/app` directory. Any files you write using <WRITE_FILE> will be available here.
4. To execute a command, output it exactly like this:
<CMD>your command</CMD>
5. To CREATE or WRITE a file, DO NOT use terminal commands. You MUST use the WRITE_FILE tool exactly like this:
<WRITE_FILE path="script.py">
import os
print("hello")
</WRITE_FILE>
6. ANTI-LAZINESS POLICY: If the Planner asks you to VERIFY or CHECK a file/result, you MUST execute a command (like `cat` or running a script) in the SAME turn to prove it works.
7. When the delegated step is fully complete, output exactly:
[STEP_COMPLETE]"""
    coder_history.append({"role": "user", "content": coder_sys})
    
    total_tokens_automode = 0
    max_swarm_cycles = 15
    
    def generate_response(bot_history, agent_name):
        nonlocal total_tokens_automode
        is_thinking = True
        def spinner():
            symbols = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
            idx = 0
            while is_thinking:
                sys.stdout.write(f"\r\033[96m{symbols[idx]}\033[0m {agent_name} is thinking...")
                sys.stdout.flush()
                idx = (idx + 1) % len(symbols)
                time.sleep(0.1)
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
            
        t = threading.Thread(target=spinner)
        t.daemon = True
        t.start()
        
        final_text = ""
        try:
            for text, delta, metrics in llm.generate(prompt="", history=bot_history, max_tokens=2048, temperature=0.4, top_k=40, top_p=0.9, override_model=planner_model if agent_name == "Planner" else coder_model, use_tools=False):
                # Do NOT stop the spinner and do NOT print delta to stdout.
                # Keep the spinner running until generation is fully complete.
                total_tokens_automode += 1
                final_text = text
            
            # Stop the spinner after the full response is generated
            if is_thinking:
                is_thinking = False
                t.join()
                
        except Exception as e:
            if is_thinking:
                is_thinking = False
                t.join()
            print(f"\n\033[91m[INTERRUPTED]\033[0m {str(e)}")
        return final_text

    successful_delegations = 0
    for cycle in range(max_swarm_cycles):
        print(f"\033[94m=== Swarm Cycle {cycle+1}/{max_swarm_cycles} ===\033[0m")
        
        # Prevent Context Overflow for Planner (Keep System Prompt + last 9 messages)
        if len(planner_history) > 10:
            planner_history = [planner_history[0]] + planner_history[-9:]
            
        planner_output = generate_response(planner_history, "Planner")
        planner_history.append({"role": "assistant", "content": planner_output})
        full_trajectory_log.append({"role": "planner", "content": planner_output})
        
        delegate_matches = re.findall(r"<DELEGATE>(.*?)(?:</DELEGATE>|$)", planner_output, re.DOTALL)
        
        if "<CONFIRM_DONE>" in planner_output and not delegate_matches:
            print(f"\033[92m[Multi-Agent Swarm]\033[0m Task completed and confirmed successfully!\n")
            break

        if "<ALL_DONE>" in planner_output and not delegate_matches:
            if successful_delegations == 0:
                print(f"\033[93m[Planner Agent]\033[0m Attempted to finish before any tasks were completed. Rejected.")
                planner_history.append({"role": "user", "content": "You cannot finish yet. You must delegate at least one step to the Coder using <DELEGATE> and it must complete successfully first."})
                continue
            else:
                # To prevent infinite loop if Planner forgets CONFIRM_DONE, we accept ALL_DONE again
                if any("Are you absolutely sure" in msg["content"] for msg in planner_history):
                    print(f"\033[92m[Multi-Agent Swarm]\033[0m Task completed and confirmed successfully!\n")
                    break
                else:
                    print(f"\033[93m[Anti-Laziness]\033[0m Verifying completion...")
                    planner_history.append({
                        "role": "user", 
                        "content": f"Are you absolutely sure you have completed ALL parts of the original task: '{initial_task}'? If you missed any step, you MUST continue using <DELEGATE>. If you are 100% sure everything is done, reply with <CONFIRM_DONE>."
                    })
                    continue
        if not delegate_matches or not any(m.strip() for m in delegate_matches):
            spam_text = planner_output.strip()
            if len(spam_text) > 300:
                spam_text = spam_text[:300] + "\n\n... [TRUNCATED] ..."
            print(f"\033[93m[Planner Agent]\033[0m {spam_text}")
            if "CONFIRM_DONE" in planner_history[-1]['content']:
                planner_history.append({"role": "user", "content": "Format error. You MUST use <DELEGATE> to continue assigning tasks, or <CONFIRM_DONE> to finalize."})
            else:
                planner_history.append({"role": "user", "content": "Format error. You MUST use <DELEGATE> to assign a task, or <ALL_DONE>."})
            continue
            
        delegate_instruction = "\n".join([m.strip() for m in delegate_matches if m.strip()])
        preview_instr = delegate_instruction.replace('\n', ' ')
        preview_instr = preview_instr if len(preview_instr) < 60 else preview_instr[:60] + "..."
        print(f"\033[95m[Planner -> Coder]\033[0m \033[96m{preview_instr}\033[0m\n")
        coder_history.append({"role": "user", "content": f"PLANNER INSTRUCTION: {delegate_instruction}"})
        
        # --- SANDBOX SETUP ---
        import shutil
        t_id = task_id if task_id else "local_task"
        sandbox_dir = os.path.abspath(os.path.join("sandbox_workspace", t_id))
        os.makedirs(sandbox_dir, exist_ok=True)
        # ---------------------
        
        coder_steps = 5
        step_completed = False
        coder_action_log = []
        for step in range(coder_steps):
            # Prevent Context Overflow for Coder (Keep System Prompt + last 9 messages)
            if len(coder_history) > 10:
                coder_history = [coder_history[0]] + coder_history[-9:]
                
            coder_output = generate_response(coder_history, "Coder")
            coder_history.append({"role": "assistant", "content": coder_output})
            full_trajectory_log.append({"role": "coder", "content": coder_output})
            
            pattern = r"<(CMD|WRITE_FILE)(?:\s+path=\"([^\"]+)\")?>\n*(.*?)\n*(?:</\1>|$)"
            actions = list(re.finditer(pattern, coder_output, re.DOTALL))
            
            if actions:
                all_success = True
                for match in actions:
                    tag_name = match.group(1)
                    file_path = match.group(2)
                    content = match.group(3)
                    
                    if tag_name == "CMD":
                        command = content.strip()
                        if not command: continue
                        
                        cmd_preview = command.replace('\n', ' ')
                        cmd_preview = cmd_preview if len(cmd_preview) < 50 else cmd_preview[:50] + "..."
                        print(f"\033[93m[Coder]\033[0m Executing: \033[96m{cmd_preview}\033[0m")
                        is_dangerous = any(keyword in command.lower() for keyword in ["rm ", "del ", "rmdir ", "rd ", "format ", "drop ", "sudo ", ">", ">>"])
                        
                        if auto_yes and not is_dangerous:
                            pass # Silent approval
                        else:
                            if is_dangerous and auto_yes:
                                print(f"\033[91m[Security Warning]\033[0m Dangerous command. Bypass overridden.")
                            choice = input(f"Allow execution? [Y/n]: ").strip().lower()
                            if choice == 'n':
                                print(f"\033[91m[Security]\033[0m Denied.\n")
                                coder_history.append({"role": "user", "content": f"Command '{command}' denied by user."})
                                all_success = False
                                break
                                
                        try:
                            # Build Docker Sandbox Command
                            docker_cmd = [
                                "docker", "run", "--rm", 
                                "--network", "none", 
                                "--memory", "512m", 
                                "--cpus", "0.5",
                                "-v", f"{sandbox_dir}:/app", 
                                "-w", "/app", 
                                "python:3.10-slim", 
                                "sh", "-c", command
                            ]
                            
                            # Check if docker exists first
                            try:
                                subprocess.run(["docker", "--version"], capture_output=True, check=True)
                                use_docker = True
                            except (subprocess.CalledProcessError, FileNotFoundError):
                                use_docker = False
                                
                            if use_docker:
                                result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=60)
                            else:
                                # Fallback to local execution if Docker is not installed (WARNING: Insecure)
                                print(f"\033[91m[WARNING]\033[0m Docker not found. Falling back to local INSECURE execution in {sandbox_dir}")
                                if os.name == 'nt':
                                    result = subprocess.run(["powershell", "-Command", command], cwd=sandbox_dir, capture_output=True, text=True, timeout=60)
                                else:
                                    result = subprocess.run(command, shell=True, cwd=sandbox_dir, capture_output=True, text=True, timeout=60)
                                    
                            stdout = result.stdout.strip()
                            stderr = result.stderr.strip()
                            output_msg = ""
                            if stdout: output_msg += f"STDOUT:\n{stdout}\n"
                            if stderr: output_msg += f"STDERR:\n{stderr}\n"
                            if not stdout and not stderr: output_msg = "Command executed successfully with no output."
                            
                            if result.returncode != 0:
                                err_preview = stderr.replace('\n', ' ')
                                err_preview = err_preview if len(err_preview) < 80 else err_preview[:80] + "..."
                                print(f"\033[91m[Failed]\033[0m {err_preview}\n")
                            else:
                                print(f"\033[92m[Success]\033[0m Command executed.\n")
                            
                            if "No such file or directory" in stderr or "Cannot find path" in stderr:
                                coder_history.append({"role": "user", "content": f"Command '{command}' failed:\n{stderr}\n\nSYSTEM WARNING: The file does not exist! Did you forget to write it using <WRITE_FILE> first?"})
                                coder_action_log.append(f"[CMD] {command}\nFailed: {stderr}")
                            else:
                                coder_history.append({"role": "user", "content": f"Command '{command}' output:\n{output_msg}"})
                                coder_action_log.append(f"[CMD] {command}\n{output_msg}")
                            
                            if result.returncode != 0:
                                all_success = False
                                break
                                
                        except subprocess.TimeoutExpired as e:
                            stdout_part = e.stdout.decode('utf-8') if isinstance(e.stdout, bytes) else (e.stdout or "")
                            print(f"\033[91m[Timeout]\033[0m Command took longer than 60s.\n")
                            coder_history.append({"role": "user", "content": f"Command timed out after 60s. Partial STDOUT:\n{stdout_part}"})
                            all_success = False
                            break
                        except Exception as e:
                            print(f"\033[91m[Error]\033[0m {str(e)}\n")
                            coder_history.append({"role": "user", "content": f"Command failed: {str(e)}"})
                            all_success = False
                            break

                    elif tag_name == "WRITE_FILE":
                        if not file_path:
                            coder_history.append({"role": "user", "content": "WRITE_FILE failed: You did not provide the path attribute. E.g. <WRITE_FILE path=\"script.py\">"})
                            all_success = False
                            break
                        
                        print(f"\033[93m[Coder]\033[0m Writing file: \033[96m{file_path}\033[0m")
                        try:
                            abs_path = os.path.abspath(os.path.join(sandbox_dir, file_path))
                            # Security check: Prevent writing outside sandbox_dir via path traversal (e.g. ../../)
                            if not abs_path.startswith(sandbox_dir):
                                raise Exception(f"Path traversal detected! Denied access to {abs_path}")
                                
                            os.makedirs(os.path.dirname(abs_path) or '.', exist_ok=True)
                            with open(abs_path, 'w', encoding='utf-8') as f:
                                f.write(content)
                            print(f"\033[92m[Success]\033[0m File written.\n")
                            coder_history.append({"role": "user", "content": f"Successfully wrote to {file_path}"})
                            coder_action_log.append(f"[WRITE_FILE] {file_path} (Success)")
                        except Exception as e:
                            print(f"\033[91m[Failed]\033[0m Could not write file: {e}\n")
                            coder_history.append({"role": "user", "content": f"Failed to write file {file_path}: {e}"})
                            coder_action_log.append(f"[WRITE_FILE] {file_path} (Failed: {e})")
                            all_success = False
                            break
                
                # If they included [STEP_COMPLETE] in the same message, process it if commands succeeded
                if "[STEP_COMPLETE]" in coder_output and all_success:
                    action_summary = "\n".join(coder_action_log)
                    if len(action_summary) > 2000: action_summary = action_summary[-2000:]
                    print(f"\033[93m[Coder Agent]\033[0m Step reported as complete.\n")
                    planner_history.append({"role": "user", "content": f"CODER REPORT: Step completed successfully.\nExecution Log:\n{action_summary}"})
                    step_completed = True
                    successful_delegations += 1
                    break
                    
            elif "[STEP_COMPLETE]" in coder_output:
                action_summary = "\n".join(coder_action_log)
                if len(action_summary) > 2000: action_summary = action_summary[-2000:]
                print(f"\033[93m[Coder Agent]\033[0m Step reported as complete.\n")
                planner_history.append({"role": "user", "content": f"CODER REPORT: Step completed successfully.\nExecution Log:\n{action_summary}"})
                step_completed = True
                successful_delegations += 1
                break
            else:
                coder_history.append({"role": "user", "content": "Use <CMD> or <WRITE_FILE> to take action, or [STEP_COMPLETE] if done."})
                
        if not step_completed:
            planner_history.append({"role": "user", "content": "CODER REPORT: Coder reached max steps without completing the task."})
    else:
        print(f"\033[93m[Multi-Agent Swarm]\033[0m Reached maximum cycles. Stopping.\n")

    # Reward for automode
    print("\033[93m[PoUW Validator]\033[0m Submitting Proof of Useful Work to ZYRA Bridge Server...")
    
    import uuid
    import shutil
    global p2p_node
    
    t_id = task_id if task_id else "local_task"
    sandbox_dir = os.path.abspath(os.path.join("sandbox_workspace", t_id))
    zip_path = os.path.abspath(f"sandbox_workspace/{t_id}_completed.zip")
    
    print(f"[\033[96mP2P Node\033[0m] Zipping workspace to {zip_path}...")
    shutil.make_archive(zip_path.replace('.zip', ''), 'zip', sandbox_dir)
    
    cid = f"P2P_LOCAL_{uuid.uuid4().hex}"
    if 'p2p_node' in globals() and p2p_node:
        print(f"[\033[96mDEBUG P2P\033[0m] Zipping workspace to {zip_path}...")
        print(f"[\033[96mDEBUG P2P\033[0m] Current peers connected: {len(p2p_node.peers)}")
        if len(p2p_node.peers) == 0:
            print("[\033[91mDEBUG P2P\033[0m] MINER IS NOT CONNECTED TO ANY P2P RELAY (0 peers)! Check Firewall Port 5050!")
        p2p_node.seed_file(cid, zip_path)
    else:
        print("[\033[91mWARNING\033[0m] P2P Node not found. File will not be seeded.")
        
    proof = PoUWValidator.generate_proof(
        task_type="AGENT_EXECUTION",
        cid=cid,
        tokens=total_tokens_automode,
        metrics={"latency_ms": 100, "vram_mb": 0.0},
        wallet_address=wallet.address
    )
    reward = proof.get('reward', 2.5)
    
    # Send to Bridge Server for real Web3 Minting
    target_wallet = wallet.metamask_address if hasattr(wallet, 'metamask_address') and wallet.metamask_address else wallet.address
    if not target_wallet:
        target_wallet = wallet.address
        
    tx_hash = "Unknown"
    try:
        response = requests.post(f"{BRIDGE_URL}/submit_pouw", json={
            "user_wallet": target_wallet,
            "trajectory_hash": proof.get('proof_hash', '0x0000'),
            "task_id": task_id,
            "reward": reward,
            "trajectory_log": cid  # ONLY SEND THE CID (Hash)
        }, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            validation_id = data.get("validation_id", "Unknown")
            print(f"\033[92m[SUCCESS]\033[0m Task submitted to Mempool! Status: \033[93mPending P2P Validation\033[0m")
            print(f"Validation ID: \033[96m{validation_id}\033[0m")
            print("Please wait for another ZYRA Node to judge your work. You can check the dashboard for updates.\n")
            
            # Save local copy for /wallet history (as pending for now)
            ledger.add_pouw_reward(target_wallet, reward, proof)
            print("\n\033[93m[System]\033[0m Waiting for validation result from network before taking new tasks...")
            try:
                start_wait = time.time()
                while time.time() - start_wait < 180:
                    status_resp = requests.get(f"{BRIDGE_URL}/validation_status/{validation_id}", timeout=5)
                    if status_resp.status_code == 200:
                        val_status = status_resp.json().get("status")
                        if val_status == "completed":
                            print("\033[92m[System]\033[0m Validation completed by the network!\n")
                            break
                    time.sleep(5)
            except Exception as e:
                pass
        elif response.status_code == 500 and response.json().get("status") == "validated_but_mint_failed":
            error_msg = response.json().get("error", "Unknown blockchain error")
            print(f"\033[93m[FALLBACK]\033[0m PoUW is Valid, but Blockchain minting failed ({error_msg}).")
            print(f"\033[92m[SUCCESS]\033[0m \033[1m+{reward:.4f} ZYRA\033[0m safely saved to your Local Offline Wallet!\n")
            ledger.add_pouw_reward(wallet.address, reward, proof)
        else:
            try:
                error_text = response.json().get("error", response.text)
            except:
                error_text = response.text
            print(f"\033[91m[REJECTED]\033[0m Bridge rejected PoUW: {error_text}\n")
            
    except requests.exceptions.RequestException as e:
        print(f"\033[91m[BRIDGE OFFLINE]\033[0m Could not connect to ZYRA Bridge Server ({BRIDGE_URL}).")
        print(f"Token reward failed. Please ensure the Bridge Server is running.\n")
        
    # Generate Audit Log File
    import datetime
    audit_filename = f"zyra_audit_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    try:
        with open(audit_filename, 'w', encoding='utf-8') as f:
            f.write(f"# ZYRA Swarm Audit Log\n\n**Task:** {initial_task}\n**Status:** {'Success' if tx_hash != 'Unknown' else 'Failed/No Reward'}\n**Transaction Hash:** {tx_hash}\n\n## Full Trajectory\n\n")
            for entry in full_trajectory_log:
                f.write(f"### {entry['role'].upper()}\n```\n{entry['content']}\n```\n\n")
        print(f"\033[92m[System]\033[0m Detailed audit log saved to \033[96m{audit_filename}\033[0m\n")
    except Exception as e:
        print(f"\033[91m[Error]\033[0m Failed to save audit log: {e}\n")
        
    # Append to global history for /export
    history.append({"role": "user", "content": f"--- AUTOMODE: {initial_task} ---"})
    for p in planner_history[1:]: # Skip system prompt
        history.append({"role": "assistant", "content": f"[Planner] {p['content']}"})
    for c in coder_history[1:]: # Skip system prompt
        history.append({"role": "assistant", "content": f"[Coder] {c['content']}"})
    history.append({"role": "user", "content": "--- END AUTOMODE ---"})


try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.styles import Style
    from prompt_toolkit.formatted_text import HTML

    def run_validator_mode(wallet: ZyraWallet, model_name: str):
        """
        Continuous looping mode to act as a P2P Smart Judge.
        Fetches pending tasks from the mempool and judges them locally.
        """
        print(f"\n\033[96m[AI Validator Node]\033[0m Starting P2P Smart Judge Mode...")
        print(f"Validator Wallet: \033[92m{wallet.address}\033[0m")
        print(f"Press \033[91mCtrl+C\033[0m to stop validating.\n")
        
        target_wallet = wallet.metamask_address if hasattr(wallet, 'metamask_address') and wallet.metamask_address else wallet.address
        
        try:
            while True:
                sys.stdout.write('\r\033[90mPolling for new tasks to validate...\033[0m')
                sys.stdout.flush()
                
                try:
                    # 1. Fetch pending task
                    resp = requests.get(f"{BRIDGE_URL}/validator/get_task", timeout=10)
                    if resp.status_code == 200:
                        sys.stdout.write('\r\033[K') # Clear line
                        task = resp.json()
                        val_id = task['validation_id']
                        miner = task['wallet']
                        print(f"[\033[93mNEW TASK\033[0m] Found pending validation \033[96m{val_id[:8]}...\033[0m from Miner \033[95m{miner[:8]}...\033[0m")
                        
                        # 2. Evaluate locally
                        global p2p_node
                        p_node = p2p_node if 'p2p_node' in globals() else None
                        is_valid, reason = PoUWValidator.evaluate_trajectory_with_llm(task['trajectory_log'], model_name, p_node)
                        
                        # 3. Submit verdict
                        print(f"[\033[96mAI Validator Node\033[0m] Submitting Verdict to Bridge Server...")
                        verdict_resp = requests.post(f"{BRIDGE_URL}/validator/submit_verdict", json={
                            "validation_id": val_id,
                            "trajectory_hash": task.get('trajectory_hash'),
                            "validator_wallet": target_wallet,
                            "is_valid": is_valid,
                            "reason": reason
                        }, timeout=30)
                        
                        if verdict_resp.status_code == 200:
                            vdata = verdict_resp.json()
                            if is_valid:
                                print(f"[\033[92mSUCCESS\033[0m] Validation accepted! Bridge Mint Tx: {vdata.get('tx_hash', 'Unknown')}\n")
                            else:
                                print(f"[\033[91mREJECTED\033[0m] Task failed validation. Reason: {reason}. Mempool cleared.\n")
                        else:
                            print(f"[\033[91mERROR\033[0m] Bridge rejected verdict submission: {verdict_resp.text}\n")
                            
                        # Brief pause before taking next task
                        time.sleep(2)
                    else:
                        # No tasks, sleep longer
                        time.sleep(5)
                except requests.exceptions.RequestException as e:
                    sys.stdout.write('\r\033[K')
                    print(f"[\033[91mConnection Error\033[0m] Could not reach Bridge Server at {BRIDGE_URL}. Retrying in 10s...")
                    time.sleep(10)
                    
        except KeyboardInterrupt:
            sys.stdout.write('\r\033[K')
            print(f"\n\033[93m[AI Validator Node]\033[0m Stopped by user.\n")

    class ZyraCommandCompleter(Completer):
        def __init__(self):
            self.commands = [
                ('/help', 'Tampilkan panduan perintah ZYRA'),
                ('/sys', 'Cek penggunaan Hardware (CPU & RAM)'),
                ('/read', 'Baca isi file teks (/read <file>)'),
                ('/search', 'Cari informasi di internet (/search <query>)'),
                ('/export', 'Simpan riwayat percakapan ke Markdown'),
                ('/link', 'Hubungkan alamat MetaMask (/link <address>)'),
                ('/claim', 'Tarik token ZYRA ke dompet Web3 (/claim <amount>)'),
                ('/stake', 'Stake token ZYRA untuk menjadi Validator (/stake <amount>)'),
                ('/automode', 'Aktifkan Swarm AI Multi-Model (/automode <task>)'),
                ('/judge', 'Run as P2P Validator Node'),
                ('/mine', 'Auto-Mining tugas dari ZYRA Network'),
                ('/models', 'Buka pengelola model lokal Ollama'),
                ('/deploy', 'Auto-deploy Smart Contract ke Localhost'),
                ('/logs', 'Lihat audit log dari tugas sebelumnya'),
                ('/clear', 'Bersihkan layar terminal dan memori percakapan'),
                ('/status', 'Alias untuk /sys (Cek Hardware)'),
                ('/config', 'Konfigurasi Wallet dan Tracker Server'),
                ('/wallet', 'Lihat saldo ZYRA dan alamat Wallet'),
                ('/submit', 'Lempar tugas coding ke jaringan (Mempool)'),
                ('exit', 'Tutup aplikasi ZYRA')
            ]

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if text.startswith('/'):
                for cmd, desc in self.commands:
                    if cmd.startswith(text):
                        yield Completion(cmd, start_position=-len(text), display=cmd, display_meta=desc)
            elif text.startswith('e'):
                if 'exit'.startswith(text):
                    yield Completion('exit', start_position=-len(text), display='exit', display_meta='Keluar dari ZYRA')

    zyra_style = Style.from_dict({
        'completion-menu.completion': 'bg:#2b2b2b #00ffff',
        'completion-menu.completion.current': 'bg:#00ffff #000000 bold',
        'completion-menu.meta.completion': 'bg:#2b2b2b #aaaaaa',
        'completion-menu.meta.completion.current': 'bg:#00ffff #000000',
    })
except ImportError:
    PromptSession = None

def main():
    global BRIDGE_URL
    global p2p_node
    
    parser = argparse.ArgumentParser(description="ZYRA Developer CLI - Agentic AI + PoUW Mining")
    parser.add_argument("prompt", type=str, nargs='?', help="The prompt or task for ZYRA AI (Optional)")
    parser.add_argument("--model", type=str, default="llama3.1:8b", help="Default Ollama model to use")
    parser.add_argument("--planner-model", type=str, default=None, help="Specific model for the Planner Agent")
    parser.add_argument("--coder-model", type=str, default=None, help="Specific model for the Coder Agent")
    parser.add_argument("--tracker", type=str, default=os.environ.get("TRACKER_URL", BRIDGE_URL), help="URL of the Tracker Server")
    parser.add_argument("--seed-peer", type=str, default=None, help="Static IP of another node to bypass tracker (e.g. ws://192.168.1.10:5001)")
    args = parser.parse_args()

    print(f"\033[92m[ZYRA CLI]\033[0m Starting Local Agentic AI...")
    
    # Initialize Core Components
    user_data_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ZYRA AI")
    wallet = ZyraWallet(user_data_dir)
    ledger = ZyraLedger(user_data_dir)
    
    print(f"Connected to Wallet: \033[96m{wallet.address}\033[0m")
    
    # Start P2P Node
    print(f"\033[94m[P2P]\033[0m Starting Gossip Node...")
    import threading
    import asyncio
    import random
    from p2p.network import P2PNode
    
    p2p_port = random.randint(5001, 5999)
    p2p_node = P2PNode(port=p2p_port, tracker_url=args.tracker, seed_peer=args.seed_peer)
    
    def p2p_judge_worker(payload):
        from app.utils.ipfs import fetch_from_ipfs
        from ai.blockchain.pouw_validator import PoUWValidator
        import threading
        
        def run_validation():
            cid = payload.get("cid")
            traj_hash = payload.get("trajectory_hash")
            
            if not cid:
                return
                
            print(f"\n\033[93m[Smart Judge]\033[0m Validating incoming Trajectory from {payload.get('wallet')} (CID: {cid})")
            
            trajectory_data = fetch_from_ipfs(cid)
            if not trajectory_data:
                print(f"\033[91m[Smart Judge]\033[0m Failed to fetch CID {cid} from IPFS.")
                return
                
            log_list = trajectory_data.get("full_log", [])
            if not log_list:
                log_list = trajectory_data.get("history", [])
                log_list.append({"role": "assistant", "content": trajectory_data.get("response", "")})
                
            is_valid, verdict_text = PoUWValidator.evaluate_trajectory_with_llm(log_list, model_name="llama3.2:1b")
            
            print(f"\033[96m[Smart Judge Verdict]\033[0m {verdict_text} ({traj_hash})")
            
            if is_valid:
                # Wallet needs sign_message, if not present we do a dummy sig
                sig = wallet.sign_message(traj_hash) if hasattr(wallet, 'sign_message') else f"SIG_{wallet.address}_{traj_hash}"
                sig_payload = {
                    "trajectory_hash": traj_hash,
                    "judge_wallet": wallet.address,
                    "signature": sig,
                    "verdict": "VALID"
                }
                p2p_node.add_signature(sig_payload)
                
                # Submit to Bridge Relayer for Minting
                try:
                    import requests
                    bridge_url = args.tracker # The tracker is also the bridge server
                    requests.post(f"{bridge_url}/validator/submit_verdict", json={
                        "trajectory_hash": traj_hash,
                        "validator_wallet": wallet.address,
                        "is_valid": True,
                        "reason": "Validated locally via IPFS"
                    }, timeout=10)
                except Exception as e:
                    print(f"\033[91m[Smart Judge]\033[0m Failed to relay verdict to bridge: {e}")
                
        threading.Thread(target=run_validation, daemon=True).start()

    p2p_node.on_trajectory_received = p2p_judge_worker
    
    def run_p2p():
        asyncio.run(p2p_node.start())
        
    p2p_thread = threading.Thread(target=run_p2p, daemon=True)
    p2p_thread.start()
    
    from zyra_cmd.installer import check_and_install_ollama, check_and_pull_model
    
    # Auto-Install Ollama Engine if missing
    check_and_install_ollama()
    
    # Check and pull model if needed
    final_model = check_and_pull_model(args.model)
    if final_model:
        args.model = final_model
    
    try:
        llm = LocalLLMGenerator(model_name=args.model)
    except Exception as e:
        print(f"\033[91m[ERROR]\033[0m Failed to connect to Ollama. Make sure Ollama is running.")
        sys.exit(1)
        
    history = []
        
    if args.prompt:
        # Single-shot mode
        process_prompt(llm, args.prompt, history, wallet, ledger, args.model)
    else:
        # Interactive REPL mode
        from importlib.metadata import version, PackageNotFoundError
        try:
            cli_version = version("zyra-network")
        except PackageNotFoundError:
            cli_version = "dev"
            
        logo = "\033[96m" + r"""
   _______  _______  ___ 
  /_  /\  \/  / _ \/ _ \ 
   / /  \    /|   / /_\ \
  / /__  |  | | |\ \  _  |
 /____/  |__| |_| \_\/ \_|
""" + "\033[0m"
        print(logo)
        print("\033[1m=================================================\033[0m")
        print(f"\033[92m    Welcome to ZYRA Interactive CLI \033[96mv{cli_version}\033[0m")
        print("\033[1m=================================================\033[0m")
        print("Type your commands below. Type \033[93m/help\033[0m for available commands, or \033[93mexit\033[0m to quit.\n")
        
        if PromptSession:
            from prompt_toolkit.patch_stdout import patch_stdout
            session = PromptSession(completer=ZyraCommandCompleter(), style=zyra_style)
        else:
            session = None
            print("\033[93m[System] Tip: Install prompt_toolkit for interactive autocomplete dropdowns!\033[0m\n")
        
        while True:
            try:
                if session:
                    with patch_stdout():
                        user_input = session.prompt("ZYRA > ").strip()
                else:
                    user_input = input("\033[96mZYRA > \033[0m").strip()
                if not user_input:
                    continue
                    
                cmd = user_input.lower()
                if cmd in ['/exit', '/quit', 'exit', 'quit']:
                    print("\033[93mGoodbye! Keep mining ZYRA.\033[0m")
                    break
                elif cmd == '/help':
                    print("\n\033[1m[ZYRA Commands]\033[0m")
                    print("  \033[93m/help\033[0m    - Show this help message")
                    print("  \033[93m/wallet\033[0m  - Show current wallet address and ZYRA balance")
                    print("  \033[93m/config\033[0m  - Configure Planner Model, EVM Wallet, and Tracker URL")
                    print("  \033[93m/clear\033[0m   - Clear terminal screen and conversation history")
                    print("  \033[93m/model\033[0m   - Change active LLM model (e.g., /model llama3.2)")
                    print("  \033[93m/sys\033[0m     - Monitor hardware (CPU & RAM usage)")
                    print("  \033[93m/read\033[0m    - Read a local file (e.g., /read script.py)")
                    print("  \033[93m/search\033[0m  - Live web search (e.g., /search latest news)")
                    print("  \033[93m/automode\033[0m- Autonomous Coding Agent (e.g., /automode create a react app)")
                    print("  \033[93m/submit\033[0m  - Submit task to ZYRA Mempool for Miners (e.g., /submit make a python script)")
                    print("  \033[93m/export\033[0m  - Save current chat history to a Markdown file")
                    print("  \033[93m/logs\033[0m    - Open the most recent PoUW Swarm Audit Log")
                    print("  \033[93m/judge\033[0m   - Run as P2P Validator Node")
                    print("  \033[93m/link\033[0m    - Link your MetaMask address (e.g., /link 0x...)")
                    print("  \033[93m/claim\033[0m   - Claim ZYRA tokens to your linked MetaMask")
                    print("  \033[93m/stake\033[0m   - Stake ZYRA tokens to become a Validator (requires CELO gas)")
                    print("  \033[93mexit\033[0m     - Exit the CLI\n")
                    continue
                elif cmd == '/logs':
                    import glob
                    audit_files = glob.glob("zyra_audit_*.md")
                    if audit_files:
                        latest_file = max(audit_files, key=os.path.getctime)
                        print(f"\033[92m[System]\033[0m Membuka log audit terakhir: \033[96m{latest_file}\033[0m")
                        if os.name == 'nt':
                            os.startfile(latest_file)
                        else:
                            try:
                                with open(latest_file, 'r', encoding='utf-8') as f:
                                    print("\n" + f.read() + "\n")
                            except:
                                print(f"File disimpan di: {latest_file}")
                    else:
                        print("\033[91m[Error]\033[0m Belum ada file log audit yang ditemukan. Jalankan /automode terlebih dahulu.\n")
                    continue
                elif cmd == '/judge':
                    run_validator_mode(wallet, llm.model_name)
                    continue
                elif cmd in ['/wallet', '/balance']:
                    balance = ledger.get_balance(wallet.address)
                    print(f"\n\033[1m[Wallet Info]\033[0m")
                    print(f"Address: \033[96m{wallet.address}\033[0m")
                    print(f"Local Offline Balance: \033[92m{balance:.4f} ZYRA\033[0m")
                    if wallet.metamask_address:
                        print(f"Linked Web3: \033[95m{wallet.metamask_address}\033[0m")
                        # Fetch Web3 balance
                        try:
                            from zyra_cmd.web3_bridge import ZyraWeb3Bridge
                            bridge = ZyraWeb3Bridge()
                            contract_addr = os.environ.get("ZYRA_CONTRACT_ADDRESS")
                            if contract_addr:
                                bridge.set_contract_address(contract_addr)
                                w3_balance = bridge.get_balance(wallet.metamask_address)
                                print(f"Web3 Balance (Celo): \033[92m{w3_balance:.4f} ZYRA\033[0m")
                        except Exception as e:
                            pass
                    print()
                    continue
                elif cmd == '/clear':
                    os.system('cls' if os.name == 'nt' else 'clear')
                    history.clear()
                    print("\033[92m[System]\033[0m Screen and conversation memory cleared.\n")
                    continue
                elif user_input.startswith('/model '):
                    new_model = user_input.split(' ', 1)[1].strip()
                    if new_model:
                        llm.model_name = new_model
                        print(f"\033[92m[System]\033[0m Model switched to: \033[96m{llm.model_name}\033[0m\n")
                    else:
                        print(f"\033[93m[System]\033[0m Current model is: \033[96m{llm.model_name}\033[0m\n")
                    continue
                elif cmd == '/model':
                    print(f"\033[93m[System]\033[0m Current model is: \033[96m{llm.model_name}\033[0m")
                    try:
                        import urllib.request, json
                        req = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
                        data = json.loads(req.read().decode('utf-8'))
                        models = [m['name'] for m in data.get('models', [])]
                        if models:
                            print("\n\033[1m[Available Models]\033[0m")
                            for m in models:
                                print(f"  - \033[96m{m}\033[0m")
                    except Exception:
                        pass
                    print("\nUse '/model <name>' to change.\n")
                    continue
                elif cmd == '/sys' or cmd == '/status':
                    try:
                        import psutil
                        cpu = psutil.cpu_percent(interval=0.5)
                        ram = psutil.virtual_memory()
                        print("\n\033[1m[Hardware Radar]\033[0m")
                        print(f"  CPU Usage: \033[96m{cpu}%\033[0m")
                        print(f"  RAM Usage: \033[96m{ram.percent}%\033[0m ({ram.used / (1024**3):.1f}GB / {ram.total / (1024**3):.1f}GB)\n")
                    except ImportError:
                        print("\033[91m[Error]\033[0m psutil library not installed.\n")
                    continue
                elif user_input.startswith('/read '):
                    filepath = user_input.split(' ', 1)[1].strip()
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                        print(f"\033[92m[System]\033[0m Successfully read {len(content)} characters from {filepath}.")
                        sys_prompt = f"I have just read the file '{filepath}'. Its content is:\n\n{content[:5000]}\n\nPlease acknowledge that you have read it and are ready to answer questions about it."
                        process_prompt(llm, sys_prompt, history, wallet, ledger, llm.model_name)
                    except Exception as e:
                        print(f"\033[91m[Error]\033[0m Could not read file: {e}\n")
                    continue
                elif user_input.startswith('/search '):
                    query = user_input.split(' ', 1)[1].strip()
                    print(f"\033[94m[System]\033[0m Searching the web for: '{query}'...")
                    try:
                        from app.utils.web_search import search_web
                        results = search_web(query, max_results=3)
                        print(f"\033[92m[System]\033[0m Search completed. Analyzing results...")
                        sys_prompt = f"I searched the web for '{query}'. Here are the latest results:\n\n{results}\n\nPlease summarize these results to answer the query."
                        process_prompt(llm, sys_prompt, history, wallet, ledger, llm.model_name)
                    except Exception as e:
                        print(f"\033[91m[Error]\033[0m Web search failed: {e}\n")
                    continue
                elif cmd == '/export':
                    import datetime
                    filename = f"zyra_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                    try:
                        with open(filename, 'w', encoding='utf-8') as f:
                            f.write("# ZYRA CLI Chat Export\n\n")
                            for msg in history:
                                role = "User" if msg['role'] == 'user' else "ZYRA"
                                f.write(f"### {role}\n{msg['content']}\n\n")
                        print(f"\033[92m[System]\033[0m Chat history exported to \033[96m{filename}\033[0m\n")
                    except Exception as e:
                        print(f"\033[91m[Error]\033[0m Failed to export: {e}\n")
                    continue
                elif user_input == '/config':
                    print("\033[94m[ZYRA Config]\033[0m")
                    model = input("\033[90mSelect Local Planner Model (e.g. llama3.1:8b): \033[0m")
                    addr = input("\033[90mEnter EVM Wallet Address: \033[0m")
                    bridge = input("\033[90mEnter Tracker Server URL (default: http://127.0.0.1:5000): \033[0m")
                    
                    global_env_dir = Path.home() / ".zyra"
                    global_env_dir.mkdir(parents=True, exist_ok=True)
                    env_file = global_env_dir / ".env"
                    
                    with open(env_file, "w") as f:
                        if model: f.write(f"PLANNER_MODEL={model}\n")
                        if addr: f.write(f"WALLET_ADDRESS={addr}\n")
                        if bridge: 
                            f.write(f"ZYRA_BRIDGE_URL={bridge}\n")
                            BRIDGE_URL = bridge
                    
                    print(f"\033[92m✓ Configuration securely saved to {env_file}\033[0m\n")
                    continue
                elif user_input.startswith('/link '):
                    addr = user_input.split(' ', 1)[1].strip()
                    if addr.startswith('0x') and len(addr) == 42:
                        wallet.metamask_address = addr
                        wallet.save()
                        print(f"\033[92m[System]\033[0m Successfully linked MetaMask address: \033[95m{addr}\033[0m\n")
                    else:
                        print(f"\033[91m[Error]\033[0m Invalid Ethereum address format.\n")
                    continue
                elif user_input.startswith('/claim'):
                    parts = user_input.split()
                    if len(parts) < 2:
                        print("\033[91m[Error]\033[0m Usage: /claim <amount>\n")
                        continue
                    try:
                        amount = float(parts[1])
                        if amount <= 0:
                            print("\033[91m[Error]\033[0m Amount must be positive.\n")
                            continue
                            
                        if not wallet.metamask_address:
                            print("\033[91m[Error]\033[0m No MetaMask address linked! Use \033[93m/link <0x_address>\033[0m first.\n")
                            continue
                            
                        balance = ledger.get_balance(wallet.address)
                        if balance < amount:
                            print(f"\033[91m[Error]\033[0m Insufficient SQLite balance! You have {balance:.4f} ZYRA.\n")
                            continue
                            
                        print(f"\033[94m[System]\033[0m Initiating Web3 Bridge to mint {amount} ZYRA...")
                        
                        try:
                            from zyra_cmd.web3_bridge import ZyraWeb3Bridge
                            bridge = ZyraWeb3Bridge()
                            
                            # Read contract address from env
                            contract_addr = os.environ.get("ZYRA_CONTRACT_ADDRESS")
                            if not contract_addr:
                                print("\033[91m[Error]\033[0m ZYRA_CONTRACT_ADDRESS tidak ditemukan di .env!\n")
                                continue
                                
                            bridge.set_contract_address(contract_addr)
                            
                            tx_hash = bridge.mint_reward(wallet.metamask_address, amount)
                            
                            # Deduct from ledger
                            ledger.add_withdraw_transaction(wallet.address, amount, tx_hash)
                            
                            print(f"\033[92m[System]\033[0m Claim successful! Tokens minted to {wallet.metamask_address}")
                            print(f"\033[96m[TxHash]\033[0m {tx_hash}\n")
                            
                        except Exception as e:
                            print(f"\033[91m[Web3 Error]\033[0m {e}\n")
                            print("Make sure you have run 'npx hardhat run scripts/deploy.js --network localhost'")
                    except ValueError:
                        print("\033[91m[Error]\033[0m Invalid amount.\n")
                    continue
                elif user_input.startswith('/stake '):
                    parts = user_input.split(' ', 1)
                    if len(parts) < 2:
                        print("\033[91m[Error]\033[0m Usage: /stake <amount>\n")
                        continue
                    try:
                        amount = float(parts[1].strip())
                        if amount <= 0:
                            print("\033[91m[Error]\033[0m Amount must be positive.\n")
                            continue
                            
                        print(f"\033[94m[System]\033[0m Initiating Staking transaction for {amount} ZYRA...")
                        try:
                            from zyra_cmd.web3_bridge import ZyraWeb3Bridge
                            bridge = ZyraWeb3Bridge()
                            
                            contract_addr = os.environ.get("ZYRA_CONTRACT_ADDRESS")
                            if not contract_addr:
                                print("\033[91m[Error]\033[0m ZYRA_CONTRACT_ADDRESS tidak ditemukan di .env!\n")
                                continue
                                
                            bridge.set_contract_address(contract_addr)
                            # Assuming CLI's wallet private_key is an EVM private key funded with CELO
                            tx_hash = bridge.stake(wallet.private_key, amount)
                            
                            print(f"\033[92m[System]\033[0m Staking successful! You can now run /judge")
                            print(f"\033[96m[TxHash]\033[0m {tx_hash}\n")
                        except Exception as e:
                            print(f"\033[91m[Web3 Error]\033[0m {e}\n(Pastikan wallet EVM anda {wallet.metamask_address or 'lokal'} memiliki saldo CELO untuk gas)\n")
                    except ValueError:
                        print("\033[91m[Error]\033[0m Invalid amount.\n")
                    continue
                elif user_input.startswith('/automode '):
                    task = user_input.split(' ', 1)[1].strip()
                    auto_yes = False
                    if task.startswith('-y '):
                        auto_yes = True
                        task = task[3:].strip()
                    elif task.startswith('--y '):
                        auto_yes = True
                        task = task[4:].strip()
                    run_automode(llm, task, history, wallet, ledger, llm.model_name, auto_yes, args.planner_model, args.coder_model)
                    continue
                elif user_input.startswith('/submit '):
                    task_prompt = user_input.split(' ', 1)[1].strip()
                    if not task_prompt:
                        print("\033[91m[Error]\033[0m Harap masukkan tugas. Contoh: /submit Buat aplikasi python...\n")
                        continue
                    
                    print(f"\033[93m[Network]\033[0m Mengirim tugas ke Mempool (Bridge Server: {BRIDGE_URL})...")
                    try:
                        resp = requests.post(f"{BRIDGE_URL}/client/submit_task", json={
                            "prompt": task_prompt,
                            "reward": 2.5
                        }, timeout=10)
                        if resp.status_code == 201:
                            data = resp.json()
                            print(f"\033[92m[Success]\033[0m Tugas berhasil dilempar ke jaringan!")
                            print(f"Task ID: \033[96m{data.get('task_id')}\033[0m")
                            print("Sekarang tinggal tunggu para Miner di jaringan untuk mengerjakan tugas ini.\n")
                            
                            # Start background thread to poll for completion
                            def wait_for_task(task_id):
                                print(f"\033[93m[Client]\033[0m Menunggu hasil validasi dari jaringan...")
                                while True:
                                    try:
                                        r = requests.get(f"{BRIDGE_URL}/client/task_status/{task_id}", timeout=5)
                                        if r.status_code == 200:
                                            res = r.json()
                                            if res.get("status") == "completed":
                                                cid = res.get("result_cid")
                                                print(f"\n\033[92m[Client]\033[0m Tugas {task_id} selesai! Mengunduh hasil (CID: {cid})...")
                                                
                                                import asyncio
                                                import tempfile
                                                
                                                dest_zip = os.path.join(os.getcwd(), f"zyra_result_{task_id[:8]}.zip")
                                                
                                                # Use threadsafe coroutine to request file
                                                future = asyncio.run_coroutine_threadsafe(
                                                    p2p_node.request_file(cid, dest_zip), 
                                                    p2p_node.loop
                                                )
                                                
                                                try:
                                                    future.result(timeout=120)
                                                    print(f"\033[92m[Success]\033[0m File berhasil diunduh ke: {dest_zip}")
                                                    # Extract it
                                                    extract_dir = os.path.join(os.getcwd(), f"zyra_workspace_{task_id[:8]}")
                                                    import zipfile
                                                    with zipfile.ZipFile(dest_zip, 'r') as zip_ref:
                                                        zip_ref.extractall(extract_dir)
                                                    print(f"\033[92m[Success]\033[0m Workspace diekstrak di: {extract_dir}\nZYRA > ", end="", flush=True)
                                                except Exception as e:
                                                    print(f"\n\033[91m[Client Error]\033[0m Gagal mengunduh file via P2P: {e}\nZYRA > ", end="", flush=True)
                                                
                                                break
                                    except Exception:
                                        pass
                                    import time
                                    time.sleep(5)
                                    
                            threading.Thread(target=wait_for_task, args=(data.get('task_id'),), daemon=True).start()
                        else:
                            print(f"\033[91m[Error]\033[0m Gagal submit: {resp.text}\n")
                    except requests.exceptions.RequestException as e:
                        print(f"\033[91m[Connection Error]\033[0m Tidak bisa terhubung ke Bridge Server ({BRIDGE_URL}).")
                        print("Pastikan konfigurasi URL Tracker sudah benar lewat perintah /config.\n")
                    continue
                elif cmd == '/deploy':
                    print("\n\033[93m[System]\033[0m Starting Auto-Deploy to Localhost...")
                    blockchain_dir = Path(__file__).resolve().parent.parent / 'blockchain'
                    if not blockchain_dir.exists():
                        print("\033[91m[Error]\033[0m 'blockchain' directory not found!\n")
                        continue
                        
                    try:
                        import subprocess, re, dotenv
                        print("\033[96m[Deploy]\033[0m Running: npx hardhat run scripts/deploy.js --network localhost")
                        # We use shell=True on Windows so 'npx' resolves correctly
                        process = subprocess.run("npx hardhat run scripts/deploy.js --network localhost", shell=True, cwd=str(blockchain_dir), capture_output=True, text=True)
                        if process.returncode != 0:
                            print(f"\033[91m[Deploy Error]\033[0m\n{process.stdout}\n{process.stderr}\n")
                            continue
                            
                        stdout = process.stdout
                        print(f"\n\033[92m[Deploy Success]\033[0m\n{stdout}")
                        
                        match = re.search(r"(0x[a-fA-F0-9]{40})", stdout)
                        if match:
                            new_addr = match.group(1)
                            print(f"\033[95m[System]\033[0m Captured new contract address: \033[96m{new_addr}\033[0m")
                            env_path = Path(__file__).resolve().parent.parent / '.env'
                            dotenv.set_key(str(env_path), "ZYRA_CONTRACT_ADDRESS", new_addr)
                            os.environ["ZYRA_CONTRACT_ADDRESS"] = new_addr
                            print("\033[92m[System]\033[0m Successfully updated .env file! ZYRA is ready to claim.\n")
                        else:
                            print("\033[91m[Error]\033[0m Could not extract 0x... address from output.\n")
                    except Exception as e:
                        print(f"\033[91m[Error]\033[0m Exception during deploy: {e}\n")
                    continue
                elif cmd == '/models':
                    import urllib.request, json, subprocess
                    try:
                        req = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
                        avail_models = [m['name'] for m in json.loads(req.read().decode('utf-8')).get('models', [])]
                        print("\n\033[1m[Installed Local Models]\033[0m")
                        if avail_models:
                            for idx, m in enumerate(avail_models, 1):
                                print(f"  {idx}. \033[96m{m}\033[0m")
                        else:
                            print("  \033[91mNo models installed yet.\033[0m")
                    except Exception as e:
                        print(f"\033[91m[Error]\033[0m Could not fetch models from Ollama: {e}\n")
                        continue
                        
                    print("\n\033[93mDo you want to install a new fresh model? (Y/n):\033[0m ", end="")
                    if input().strip().lower() != 'n':
                        print("\n\033[1m[Fresh Model Recommendations]\033[0m")
                        print("  1. \033[96mdeepseek-r1:7b\033[0m  - [Reasoning] The new highly capable reasoning model")
                        print("  2. \033[96mqwen2.5-coder:32b\033[0m- [Heavy] The ultimate Coder (Requires 24GB+ RAM)")
                        print("  3. \033[96mqwen2.5-coder:7b\033[0m - [Coding] The best small model for code generation")
                        print("  4. \033[96mphi4\033[0m             - [Balanced] Microsoft's latest compact but smart model")
                        print("  5. \033[95mCustom (Type your own model name from ollama.com)\033[0m")
                        
                        choices = {'1': 'deepseek-r1:7b', '2': 'qwen2.5-coder:32b', '3': 'qwen2.5-coder:7b', '4': 'phi4'}
                        ans = input("\n\033[93mEnter number (1-5): \033[0m").strip()
                        
                        target_model = None
                        if ans in choices:
                            target_model = choices[ans]
                        elif ans == '5':
                            target_model = input("\033[93mEnter exact model name: \033[0m").strip()
                            
                        if target_model:
                            print(f"\n\033[94m[System]\033[0m Pulling {target_model} from Ollama registry...")
                            try:
                                process = subprocess.run(["ollama", "pull", target_model])
                                if process.returncode == 0:
                                    print(f"\n\033[92m[System]\033[0m {target_model} successfully downloaded!\n")
                                else:
                                    print(f"\n\033[91m[Error]\033[0m Failed to pull model.\n")
                            except Exception as e:
                                print(f"\n\033[91m[Error]\033[0m Failed to execute ollama pull: {e}\n")
                        else:
                            print("\033[91mInvalid choice.\033[0m\n")
                    else:
                        print()
                    continue
                elif cmd == '/mine':
                    print("\n\033[93m[Miner]\033[0m Starting ZYRA Auto-Miner...")
                    print("\033[96m[System]\033[0m Polling network for new tasks (Press Ctrl+C to stop)...\n")
                    target_wallet = wallet.metamask_address if hasattr(wallet, 'metamask_address') and wallet.metamask_address else wallet.address
                    if not target_wallet: target_wallet = wallet.address
                    
                    try:
                        import time
                        while True:
                            try:
                                resp = requests.get(f"{BRIDGE_URL}/miner/get_task", params={"wallet": target_wallet}, timeout=5)
                                if resp.status_code == 200:
                                    task_data = resp.json()
                                    task_id = task_data.get("task_id")
                                    prompt = task_data.get("prompt")
                                    reward = task_data.get("reward")
                                    print(f"\n\033[92m[Network]\033[0m Found Task! Reward: {reward} ZYRA")
                                    run_automode(llm, prompt, history, wallet, ledger, llm.model_name, auto_yes=True, planner_model=args.planner_model, coder_model=args.coder_model, task_id=task_id)
                                    print("\n\033[96m[System]\033[0m Polling network for next task...\n")
                                else:
                                    time.sleep(10) # Wait 10 seconds before polling again
                            except requests.exceptions.RequestException:
                                print(f"\033[91m[Error]\033[0m Cannot connect to Bridge Server. Retrying in 10s...")
                                time.sleep(10)
                    except KeyboardInterrupt:
                        print("\n\033[93m[Miner]\033[0m Auto-Miner stopped.\033[0m\n")
                    continue
                
                # If not a slash command, process as AI prompt
                process_prompt(llm, user_input, history, wallet, ledger, llm.model_name)
                
            except KeyboardInterrupt:
                print("\n\033[93mInterrupted. Type 'exit' to quit.\033[0m")
            except EOFError:
                break

if __name__ == "__main__":
    main()
