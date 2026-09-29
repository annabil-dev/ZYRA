import os
import sys
import time
import json
import json as _json
import argparse
import subprocess
import re
import requests
from pathlib import Path

# Fix Windows console encoding & ANSI colors
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    try:
        import colorama
        colorama.just_fix_windows_console()
    except ImportError:
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

BRIDGE_URL = os.environ.get("ZYRA_BRIDGE_URL", "https://zyra-ai.tail3b049d.ts.net") # Hardcoded Global Bootstrap Node (Mythchain Alpha Tracker)


def get_pending_miner_task(tasks, preferred_task_id=None, miner_identity=None, now=None, canonical_mode=False):
    """Return (task_id, task) or None; empty mempools are a normal state."""
    import time as _time
    from p2p.leases import verify_lease
    now = _time.time() if now is None else now

    def eligible(task):
        if canonical_mode or task.get("lease_mode") == "mythchain":
            return task.get("status") in ("pending", "mining")
        lease = task.get("lease")
        if lease and verify_lease(lease, task, now):
            return task.get("status") in ("pending", "mining") and lease.get("miner_identity") == miner_identity
        return task.get("status") in ("pending", "mining")

    if preferred_task_id:
        preferred = tasks.get(preferred_task_id)
        if preferred and preferred.get("status") == "pending" and eligible(preferred):
            return preferred_task_id, preferred
    for task_id, task in list(tasks.items()):
        if eligible(task):
            return task_id, task
    return None


def claim_mythchain_task(task_id, acceptance_hash, role="miner", config=None, adapter_factory=None, criteria=None):
    """Claim a task through Mythchain and return (config, canonical lease)."""
    from zyra_cmd.mythchain_adapter import MythchainConfig, MythchainTaskAdapter
    chain_config = config or MythchainConfig.from_env(role)
    adapter = (adapter_factory or MythchainTaskAdapter)(chain_config)
    return chain_config, adapter.claim_task(task_id, acceptance_hash, criteria=criteria)

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
    # Generate a local CID for the trajectory (served via P2P, no centralized IPFS needed)
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


def run_automode(llm, initial_task: str, history: list, wallet: ZyraWallet, ledger: ZyraLedger, model_name: str, auto_yes: bool = False, planner_model: str = None, coder_model: str = None, task_id: str = None, attempt_id: str = None, canonical_attempt_id: str = None):
    global p2p_node
    import uuid
    from ai.execution.contract import make_contract, validate_contract, contract_hash, delivery_instructions, deliverable_files
    from ai.execution.runtime import ensure_runtime, execute_miner_command, validate_workspace
    try:
        runtime_image = ensure_runtime()
        if task_id:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", task_id):
                raise ValueError("Invalid task ID")
            acceptance = validate_contract(p2p_node.tasks[task_id].get("acceptance"))
            if p2p_node.tasks[task_id].get("acceptance_hash") != contract_hash(acceptance):
                raise ValueError("Task acceptance hash mismatch")
            current_lease = p2p_node.tasks[task_id].get("lease")
            if current_lease and (current_lease.get("lease_id") != attempt_id or current_lease.get("miner_identity") != (wallet.signing_address or wallet.address)):
                raise ValueError("This miner no longer owns the current task lease")
        else:
            task_id = str(uuid.uuid4())
            acceptance = make_contract(initial_task)
            if 'p2p_node' in globals():
                p2p_node.add_task({"task_id": task_id, "prompt": initial_task, "status": "mining",
                                   "client": wallet.metamask_address or wallet.address,
                                   "acceptance": acceptance, "acceptance_hash": contract_hash(acceptance)})
    except Exception as exc:
        print(f"[Runtime] Cannot start task: {exc}")
        return False
    delivery_rules = delivery_instructions(acceptance)
    work_verified = False
    validation_report = None
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
1. **TDD REQUIRED**: Before delegating the main code to the Coder, you MUST write a strict mathematical Unit Test using Python's built-in `unittest` module and save it as `test_suite.py`. This test suite must verify the correctness of the Coder's future work.
2. To write the test suite, use exactly this format:
<WRITE_FILE path="test_suite.py">
import unittest
...
</WRITE_FILE>
3. After writing the test suite, delegate to the CODER AGENT using exactly this format:
<DELEGATE>instruction for coder</DELEGATE>
4. Wait for the Coder to report completion before sending the next <DELEGATE>. DO NOT send multiple <DELEGATE> tags in a single message.
5. You CANNOT execute terminal commands. You only plan, write test suites, and delegate.
6. DO NOT output <ALL_DONE> until you have verified all steps are truly finished and the tests pass.
7. When the entire task is truly finished, output exactly:
<ALL_DONE>
8. If the system asks you to confirm completion, and you are 100% sure, reply exactly:
<CONFIRM_DONE>"""
    planner_sys += "\n" + delivery_rules
    planner_history.append({"role": "user", "content": planner_sys})
    
    coder_sys = """You are the CODER AGENT running in the shared ZYRA Python Docker runtime.
You will receive instructions from the PLANNER.
RULES:
1. You are on Linux. DO NOT use Windows/PowerShell commands. Use standard Linux commands (e.g., `ls`, `cat`, `python`).
2. Your environment has NO internet at execution time. Real Flask is PREINSTALLED. Use the installed libraries or standard library; never replace required libraries with mocks. Do not run pip install.
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
[STEP_COMPLETE]
8. If given an independent DELIVERY VALIDATOR report, treat it as a blocking requirement. Do not claim a fix after only reading files or rerunning tests; use <WRITE_FILE> to make the required change, then run a relevant verification. Preserve the client's acceptance hash and run command exactly."""
    coder_sys += "\n" + delivery_rules
    coder_history.append({"role": "user", "content": coder_sys})
    
    total_tokens_automode = 0
    max_swarm_cycles = 15
    audit_path = os.path.abspath(os.path.join("sandbox_workspace", "_audit", f"{task_id}.jsonl"))
    os.makedirs(os.path.dirname(audit_path), exist_ok=True)

    def audit_event(event, **details):
        """Persist swarm diagnostics outside the deliverable workspace."""
        record = {"timestamp": time.time(), "task_id": task_id, "attempt_id": attempt_id,
                  "event": event, **details}
        try:
            with open(audit_path, "a", encoding="utf-8") as audit_file:
                audit_file.write(_json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            print(f"[Audit] Could not write {audit_path}: {exc}")
    
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
    pending_delivery_feedback = None
    feedback_change_made = False
    for cycle in range(max_swarm_cycles):
        print(f"\033[94m=== Swarm Cycle {cycle+1}/{max_swarm_cycles} ===\033[0m")
        audit_event("cycle_started", cycle=cycle + 1, max_cycles=max_swarm_cycles)
        
        # Prevent Context Overflow for Planner (Keep System Prompt + last 9 messages)
        if len(planner_history) > 10:
            planner_history = [planner_history[0]] + planner_history[-9:]
            
        # --- SANDBOX SETUP ---
        t_id = task_id if task_id else "local_task"
        sandbox_dir = os.path.abspath(os.path.join("sandbox_workspace", t_id))
        os.makedirs(sandbox_dir, exist_ok=True)
        # ---------------------
            
        planner_output = generate_response(planner_history, "Planner")
        audit_event("planner_response", cycle=cycle + 1, content=planner_output)
        planner_history.append({"role": "assistant", "content": planner_output})
        full_trajectory_log.append({"role": "planner", "content": planner_output})
        
        write_pattern = r"<WRITE_FILE(?:\s+path=\"([^\"]+)\")?>\n*(.*?)\n*(?:</WRITE_FILE>|$)"
        write_matches = list(re.finditer(write_pattern, planner_output, re.DOTALL | re.IGNORECASE))
        if write_matches:
            for match in write_matches:
                file_path = match.group(1)
                content = match.group(2)
                if file_path:
                    print(f"\033[93m[Planner Agent]\033[0m Writing file: \033[96m{file_path}\033[0m")
                    try:
                        abs_path = os.path.abspath(os.path.join(sandbox_dir, file_path))
                        if not Path(abs_path).is_relative_to(Path(sandbox_dir)):
                            raise Exception("Path traversal denied")
                        os.makedirs(os.path.dirname(abs_path) or '.', exist_ok=True)
                        with open(abs_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        if pending_delivery_feedback:
                            feedback_change_made = True
                        planner_history.append({"role": "user", "content": f"Successfully wrote to {file_path}"})
                    except Exception as e:
                        print(f"\033[91m[Failed]\033[0m {e}\n")
                        planner_history.append({"role": "user", "content": f"Failed to write file {file_path}: {e}"})
        
        delegate_matches = re.findall(r"<DELEGATE>(.*?)(?:</DELEGATE>|$)", planner_output, re.DOTALL)
        
        if any(tag in planner_output for tag in ("<ALL_DONE>", "<CONFIRM_DONE>")) and not delegate_matches:
            if successful_delegations == 0:
                print(f"\033[93m[Planner Agent]\033[0m Attempted to finish before any tasks were completed. Rejected.")
                planner_history.append({"role": "user", "content": "You cannot finish yet. You must delegate at least one step to the Coder using <DELEGATE> and it must complete successfully first."})
                continue
            print("[Runtime] Checking documentation, all tests, and actual application startup...")
            work_verified, validation_report = validate_workspace(sandbox_dir, acceptance)
            if work_verified:
                print("[Runtime] Delivery checks passed. Ready for independent network validation.\n")
                pending_delivery_feedback = None
                break
            feedback = str(validation_report)[-6000:]
            pending_delivery_feedback = feedback
            feedback_change_made = False
            audit_event("delivery_rejected", cycle=cycle + 1, report=validation_report)
            planner_history.append({"role": "user", "content": (
                "DELIVERY REJECTED by the independent pre-delivery validator. Fix the concrete reported issue "
                "before claiming completion. Inspect the named file(s), then either remove unintended temporary/debug "
                "files or document every retained deliverable in BOTH README.md and zyra.json. If startup or a test "
                "failed, reproduce and fix that exact failure; do not weaken the client acceptance contract. "
                "Delegate the fix to the Coder and require it to run a relevant verification command.\n"
                f"Validator report: {feedback}\nAudit log: {audit_path}"
            )})
            print(f"[Runtime] Delivery rejected: {validation_report.get('reason')}")
            if validation_report.get("status") == "UNAVAILABLE":
                break
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
        if pending_delivery_feedback:
            coder_history.append({"role": "user", "content": (
                "INDEPENDENT DELIVERY FIX REQUIRED. The previous delivery was rejected. "
                "Read this exact validator report, change the named deliverable(s) using WRITE_FILE, "
                "and run a relevant verification. Do not only inspect the files or rerun passing tests. "
                "Do not remove required files or change the client's acceptance contract.\n"
                f"Validator report: {pending_delivery_feedback}"
            )})
        

        coder_steps = 5
        step_completed = False
        coder_action_log = []
        for step in range(coder_steps):
            # Prevent Context Overflow for Coder (Keep System Prompt + last 9 messages)
            if len(coder_history) > 10:
                coder_history = [coder_history[0]] + coder_history[-9:]
                
            coder_output = generate_response(coder_history, "Coder")
            audit_event("coder_response", cycle=cycle + 1, step=step + 1, content=coder_output)
            coder_history.append({"role": "assistant", "content": coder_output})
            full_trajectory_log.append({"role": "coder", "content": coder_output})

            has_write_file = re.search(r"<WRITE_FILE(?:\s+path=\"[^\"]+\")?>", coder_output,
                                        re.IGNORECASE) is not None
            if (pending_delivery_feedback and "[STEP_COMPLETE]" in coder_output
                    and not feedback_change_made and not has_write_file):
                print("[Coder Agent] Validator fix not complete: inspect-only/test-only step rejected.")
                coder_history.append({"role": "user", "content": (
                    "Do not mark the delivery fix complete yet: this turn did not write a corrected file. "
                    "Use <WRITE_FILE path=\"...\"> to fix the exact validator issue, then verify it."
                )})
                audit_event("coder_fix_completion_rejected", cycle=cycle + 1, step=step + 1,
                            reason="No file change after validator rejection")
                continue
            
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
                            result = execute_miner_command(sandbox_dir, command, runtime_image)
                                    
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
                            audit_event("command_result", cycle=cycle + 1, step=step + 1,
                                        command=command, returncode=result.returncode,
                                        stdout=stdout, stderr=stderr)
                            
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
                            if not Path(abs_path).is_relative_to(Path(sandbox_dir)):
                                raise Exception(f"Path traversal detected! Denied access to {abs_path}")
                                
                            os.makedirs(os.path.dirname(abs_path) or '.', exist_ok=True)
                            with open(abs_path, 'w', encoding='utf-8') as f:
                                f.write(content)
                            if pending_delivery_feedback:
                                feedback_change_made = True
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
        audit_event("max_cycles_reached", max_cycles=max_swarm_cycles)
        print(f"[Audit] Per-cycle diagnostic log: {audit_path}")
        if (not work_verified and isinstance(validation_report, dict)
                and validation_report.get("delivery_ready")
                and isinstance(validation_report.get("criteria_results"), dict)):
            # Submit the final measurable partial result so independent judges can
            # score it; the chain outcome/payout follows the canonical rubric.
            work_verified = True
            print("[Runtime] Swarm cycles exhausted; submitting the measured partial result for independent judging.\n")

    if not work_verified:
        print("[Runtime] Task is not deliverable. No trajectory or reward submitted.\n")
        return False

    if task_id and attempt_id:
        from p2p.leases import verify_lease
        current_task = p2p_node.tasks.get(task_id, {})
        if current_task.get("attempt_id") != attempt_id or not verify_lease(current_task.get("lease"), current_task):
            print("[P2P Lease] This task attempt expired or lost its lease. Result will not be submitted.")
            return False

    if task_id and canonical_attempt_id:
        from zyra_cmd.mythchain_adapter import MythchainConfig, MythchainTaskAdapter
        try:
            chain_config = MythchainConfig.from_env("miner")
            canonical = MythchainTaskAdapter(chain_config).query_task(task_id)
        except Exception as exc:
            print(f"[Mythchain] Cannot confirm canonical lease before delivery: {exc}")
            return False
        if (not canonical
                or canonical.get("attempt_id", canonical.get("attemptId")) != canonical_attempt_id
                or canonical.get("miner_address", canonical.get("minerAddress")) != chain_config.address
                or str(canonical.get("status", "")).upper() != "LEASED"):
            print("[Mythchain] Canonical task lease changed or expired. Result will not be submitted.")
            return False

    # Reward for automode
    print("\033[93m[PoUW Validator]\033[0m Submitting Proof of Useful Work to P2P Network...")
    
    import uuid
    import shutil
    
    t_id = task_id if task_id else "local_task"
    sandbox_dir = os.path.abspath(os.path.join("sandbox_workspace", t_id))
    zip_path = os.path.abspath(f"sandbox_workspace/{t_id}_completed.zip")
    
    print(f"[\033[96mP2P Node\033[0m] Zipping workspace to {zip_path}...")
    import zipfile
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in deliverable_files(sandbox_dir):
            archive.write(Path(sandbox_dir) / name, name)
    
    from p2p.content import content_cid
    cid = content_cid(zip_path)
    if 'p2p_node' in globals() and p2p_node:
        if len(p2p_node.peers) == 0:
            print("[\033[91mWARNING\033[0m] MINER IS NOT CONNECTED TO ANY P2P RELAY (0 peers)! Check Firewall Port 5050!")
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

    chain_result_committed = False
    if task_id and canonical_attempt_id:
        try:
            from zyra_cmd.mythchain_adapter import MythchainConfig, MythchainTaskAdapter
            chain_config = MythchainConfig.from_env("miner")
            canonical_result = MythchainTaskAdapter(chain_config).submit_task_result(
                task_id, canonical_attempt_id, cid, proof["proof_hash"])
            print(f"[Mythchain] Result committed for canonical attempt {canonical_result.get('attempt_id', canonical_result.get('attemptId'))}.")
            chain_result_committed = True
            p2p_node.tasks[task_id]["chain_attempt_id"] = canonical_attempt_id
            p2p_node.tasks[task_id]["chain_result_cid"] = cid
        except Exception as exc:
            print(f"[Mythchain] Result was not committed; P2P submission stopped: {exc}")
            return False
    
    target_wallet = wallet.metamask_address if hasattr(wallet, 'metamask_address') and wallet.metamask_address else wallet.address
    if not target_wallet:
        target_wallet = wallet.address
        
    network_status = "pending"
    try:
        from p2p.protocol import MessageType, create_message
        import asyncio
        
        traj_hash = proof.get('proof_hash', f"0x{uuid.uuid4().hex}")
        
        # 1. Broadcast trajectory to P2P for judges to pick up
        traj_payload = {
            "trajectory_hash": traj_hash,
            "task_id": task_id,
            "wallet": target_wallet,
            "trajectory_log": cid,
            "acceptance_hash": contract_hash(acceptance),
            "attempt_id": attempt_id or "",
            "chain_attempt_id": canonical_attempt_id or "",
            "reward": reward,
            "status": "pending_validation",
            "miner_identity": wallet.signing_address or wallet.address,
            "miner_public_key": wallet.signing_public_key or wallet.public_key
        }
        p2p_node.trajectories[traj_hash] = traj_payload
        traj_msg = create_message(MessageType.NEW_TRAJECTORY, traj_payload)
        asyncio.run_coroutine_threadsafe(p2p_node.broadcast(traj_msg), p2p_node.loop)
        
        # 2. Update task status to "validating" in the P2P mempool
        if task_id and task_id in p2p_node.tasks:
            p2p_node.tasks[task_id]["status"] = "validating"
            p2p_node.tasks[task_id]["result_cid"] = cid
            p2p_node.tasks[task_id]["trajectory_hash"] = traj_hash
            update_msg = create_message(MessageType.TASK_UPDATED, p2p_node.tasks[task_id])
            asyncio.run_coroutine_threadsafe(p2p_node.broadcast(update_msg), p2p_node.loop)
        
        print(f"\033[92m[SUCCESS]\033[0m Task submitted to P2P Mempool! Status: \033[93mPending P2P Validation\033[0m")
        print(f"Trajectory Hash: \033[96m{traj_hash[:16]}...\033[0m")
        print("Waiting for Smart Judges to validate your work...\n")
        
        # Credit only after network approval; failed/pending work is not earned balance.
        
        # Wait for validation result from P2P gossip (check signatures)
        print("\033[93m[System]\033[0m Waiting for validation signatures from P2P network...")
        try:
            start_wait = time.time()
            while time.time() - start_wait < 180:
                if canonical_attempt_id:
                    try:
                        from zyra_cmd.mythchain_adapter import MythchainConfig, MythchainTaskAdapter
                        chain_config = MythchainConfig.from_env("miner")
                        canonical = MythchainTaskAdapter(chain_config).query_task(task_id)
                        chain_attempt = canonical.get("attempt_id", canonical.get("attemptId")) if canonical else None
                        chain_status = str(canonical.get("status", "")).upper() if canonical else ""
                        if chain_attempt != canonical_attempt_id or not canonical:
                            network_status = "canonical attempt changed"
                            print("[Mythchain] Attempt changed during judge voting; no local reward credited.")
                            break
                        if chain_status == "APPROVED":
                            ledger.add_pouw_reward(target_wallet, reward, proof, task_id=task_id)
                            network_status = "Mythchain APPROVED (local ledger credit only)"
                            print("[Mythchain] Canonical judge quorum APPROVED the result.\n")
                            break
                        if chain_status == "REJECTED":
                            network_status = "Mythchain REJECTED"
                            print("[Mythchain] Canonical judge quorum REJECTED the result; no reward credited.\n")
                            break
                    except Exception as exc:
                        print(f"[Mythchain] Waiting for canonical judge state: {exc}")
                    time.sleep(3)
                    continue
                from p2p.votes import tally
                verdict = tally(p2p_node.signatures.get(traj_hash, {}))
                if verdict == "FAIL":
                    network_status = "rejected"
                    print(f"[Judge -> Miner] Rejected: {p2p_node.tasks.get(task_id, {}).get('feedback', [])}. No reward credited.")
                    break
                sigs = p2p_node.signatures.get(traj_hash, {})
                if p2p_node.tasks.get(task_id, {}).get("status") == "completed" and verdict == "PASS":
                    ledger.add_pouw_reward(target_wallet, reward, proof, task_id=task_id)
                    network_status = "validated (local reward credited)"
                    print("\033[92m[System]\033[0m Quorum of 2 distinct judges approved this task!\n")
                    break
                if len(sigs) == 1:
                    print("[Miner] One verified judge vote received. Waiting for second judge...")
                time.sleep(3)
            else:
                print("\033[93m[System]\033[0m Validation still pending. Waiting for quorum; Ctrl+C stops mining.\n")
                if task_id:
                    if canonical_attempt_id:
                        while True:
                            from zyra_cmd.mythchain_adapter import MythchainConfig, MythchainTaskAdapter
                            canonical = MythchainTaskAdapter(MythchainConfig.from_env("miner")).query_task(task_id)
                            if not canonical or canonical.get("attempt_id", canonical.get("attemptId")) != canonical_attempt_id:
                                network_status = "canonical attempt changed"
                                break
                            status = str(canonical.get("status", "")).upper()
                            if status == "APPROVED":
                                ledger.add_pouw_reward(target_wallet, reward, proof, task_id=task_id)
                                network_status = "Mythchain APPROVED (local ledger credit only)"
                                break
                            if status == "REJECTED":
                                network_status = "Mythchain REJECTED"
                                break
                            time.sleep(3)
                    else:
                        while tally(p2p_node.signatures.get(traj_hash, {})) is None:
                            time.sleep(3)
                        if tally(p2p_node.signatures[traj_hash]) == "PASS" and p2p_node.tasks[task_id]["status"] == "completed":
                            ledger.add_pouw_reward(target_wallet, reward, proof, task_id=task_id)
                            network_status = "validated (local reward credited)"
                        elif tally(p2p_node.signatures[traj_hash]) == "FAIL":
                            network_status = "rejected"
                            print(f"[Judge -> Miner] Rejected: {p2p_node.tasks.get(task_id, {}).get('feedback', [])}")
        except KeyboardInterrupt:
            print("[Miner] Validation is still pending. No reward credited. Stopping this mining session.")
            raise
            
    except Exception as e:
        network_status = "submission_error"
        print(f"\033[91m[P2P Error]\033[0m Could not broadcast to P2P network: {e}")
        print("No reward credited without network validation.\n")
        
        
    # Generate Audit Log File
    import datetime
    audit_filename = f"zyra_audit_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    try:
        with open(audit_filename, 'w', encoding='utf-8') as f:
            f.write(f"# ZYRA Swarm Audit Log\n\n**Task:** {initial_task}\n**Network status:** {network_status}\n"
                    f"**Mythchain result:** {'Committed' if chain_result_committed else 'Not submitted by this flow'}\n"
                    "**Mythchain judge votes/settlement:** Votes are submitted by judge nodes; native reward settlement is not implemented.\n\n"
                    "## Local delivery verification\n\n")
            import json
            f.write("```json\n" + json.dumps(validation_report, indent=2) + "\n```\n\n## Full Trajectory\n\n")
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
    return True


try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.styles import Style
    from prompt_toolkit.formatted_text import HTML

    def run_validator_mode(wallet: ZyraWallet, model_name: str):
        """
        Continuous looping mode to act as a P2P Smart Judge.
        Scans P2P Mempool for pending trajectories and validates them locally.
        """
        print(f"\n\033[96m[AI Validator Node]\033[0m Starting P2P Smart Judge Mode...")
        print(f"Validator Wallet: \033[92m{wallet.address}\033[0m")
        print(f"Press \033[91mCtrl+C\033[0m to stop validating.\n")
        
        target_wallet = wallet.metamask_address if hasattr(wallet, 'metamask_address') and wallet.metamask_address else wallet.address

        from ai.execution.runtime import ensure_runtime
        from ai.execution.contract import contract_hash
        from p2p.votes import judge_address
        try:
            if judge_address(wallet.signing_public_key or wallet.public_key) != (wallet.signing_address or wallet.address):
                raise ValueError("Local signing identity does not match its public key")
            ensure_runtime()
        except Exception as exc:
            print(f"[Smart Judge] {exc}. A real ECDSA wallet is required for judge votes.")
            return
        
        # --- SYBIL RESISTANCE (STAKING CHECK) ---
        import os
        contract_addr = os.environ.get("ZYRA_CONTRACT_ADDRESS")
        if contract_addr and target_wallet.startswith("0x"):
            try:
                from zyra_cmd.web3_bridge import ZyraWeb3Bridge
                bridge = ZyraWeb3Bridge()
                bridge.set_contract_address(contract_addr)
                staked_bal = bridge.get_staked_balance(target_wallet)
                if staked_bal < 10.0:
                    print(f"\033[91m[Access Denied]\033[0m You need to stake at least 10 ZYRA to become a Smart Judge.")
                    print(f"Your current staked balance: {staked_bal:.2f} ZYRA.")
                    print(f"Use \033[93m/stake 10\033[0m to lock your tokens.\n")
                    return
                print(f"\033[92m[Verified]\033[0m Judge Stake Confirmed: {staked_bal:.2f} ZYRA locked.")
            except Exception as e:
                print(f"\033[91m[Warning]\033[0m Could not verify staked balance on Celo: {e}")
        else:
            print(f"\033[93m[Warning]\033[0m Contract Address or MetaMask not linked. Skipping on-chain stake verification for prototype testing.")
        # ----------------------------------------
        
        validated_trajs = set()  # Track what we already judged
        
        try:
            while True:
                sys.stdout.write('\r\033[90mPolling P2P Mempool for new tasks to validate...\033[0m')
                sys.stdout.flush()
                
                # Scan P2P mempool for pending trajectories
                found_traj = None
                for traj_hash, traj_data in list(p2p_node.trajectories.items()):
                    if traj_hash not in validated_trajs and traj_data.get("status") == "pending_validation":
                        # Don't judge your own work
                        if traj_data.get("miner_identity") != (wallet.signing_address or wallet.address) and traj_data.get("wallet") != target_wallet:
                            found_traj = (traj_hash, traj_data)
                            break
                
                if found_traj:
                    traj_hash, task = found_traj
                    validated_trajs.add(traj_hash)
                    
                    sys.stdout.write('\r\033[K')  # Clear line
                    miner = task.get('wallet', 'Unknown')
                    print(f"[\033[93mNEW TASK\033[0m] Found pending validation \033[96m{traj_hash[:8]}...\033[0m from Miner \033[95m{miner[:8]}...\033[0m")
                    
                    # Evaluate locally
                    p_node = p2p_node if 'p2p_node' in globals() else None
                    original_task = p2p_node.tasks.get(task.get("task_id"))
                    if original_task is None:
                        validated_trajs.discard(traj_hash)
                        print("[Smart Judge] Waiting for original task acceptance criteria from P2P sync.")
                        time.sleep(5)
                        continue
                    acceptance = original_task.get("acceptance")
                    try:
                        from p2p.leases import verify_lease
                        if task.get("attempt_id"):
                            if (original_task.get("attempt_id") != task["attempt_id"]
                                    or not verify_lease(original_task.get("lease"), original_task)):
                                raise ValueError("Miner work lease is missing, expired, or superseded")
                        expected_hash = contract_hash(acceptance)
                        if original_task.get("acceptance_hash") != expected_hash or task.get("acceptance_hash") != expected_hash:
                            raise ValueError("Submission does not match the original task acceptance hash")
                        is_valid, reason = PoUWValidator.evaluate_trajectory_with_llm(
                            task['trajectory_log'], model_name, p_node, acceptance=acceptance)
                    except (ValueError, TypeError, AttributeError) as exc:
                        is_valid, reason = False, {"status": "FAILED", "reason": str(exc), "retry": False}
                    if isinstance(reason, dict) and reason.get("status") == "UNAVAILABLE":
                        validated_trajs.discard(traj_hash)
                        print(f"[Smart Judge] Validation deferred: {reason.get('reason')}")
                        time.sleep(10)
                        continue

                    acceptance = original_task.get("acceptance") or {}
                    weighted_criteria = acceptance.get("criteria") if isinstance(acceptance, dict) else None
                    criteria_results = reason.get("criteria_results") if isinstance(reason, dict) else None
                    if weighted_criteria:
                        if not isinstance(criteria_results, dict):
                            validated_trajs.discard(traj_hash)
                            print("[Smart Judge] Weighted acceptance checks need per-criterion results; "
                                  "no vote submitted until the evaluator provides them.")
                            time.sleep(10)
                            continue
                    
                    # Submit verdict via P2P
                    print(f"[\033[96mAI Validator Node\033[0m] Submitting Verdict to P2P Network...")
                    
                    from p2p.protocol import MessageType, create_message
                    import asyncio
                    
                    from p2p.votes import sign_vote
                    error_text = reason if isinstance(reason, str) else reason.get("reason", str(reason))
                    vote = sign_vote(wallet, task, "PASS" if is_valid else "FAIL",
                                     "" if is_valid else error_text, criteria_results=criteria_results)
                    chain_attempt_id = task.get("chain_attempt_id")
                    if original_task.get("lease_mode") == "mythchain":
                        if not chain_attempt_id:
                            validated_trajs.discard(traj_hash)
                            print("[Mythchain] Missing canonical attempt ID; judge vote deferred.")
                            time.sleep(5)
                            continue
                        try:
                            from zyra_cmd.mythchain_adapter import MythchainConfig, MythchainTaskAdapter
                            chain_state = MythchainTaskAdapter(MythchainConfig.from_env("judge")).vote_task(
                                task["task_id"], chain_attempt_id,
                                "PASS" if is_valid else "FAIL",
                                "" if is_valid else error_text,
                                acceptance_hash=expected_hash,
                                result_cid=task["trajectory_log"],
                                criteria_results=criteria_results if weighted_criteria else None,
                                criteria=weighted_criteria)
                            chain_status = str(chain_state.get("status", "")).upper()
                            print(f"[Mythchain] Judge vote committed. Canonical status: {chain_status}.")
                        except Exception as exc:
                            validated_trajs.discard(traj_hash)
                            print(f"[Mythchain] Judge vote not committed; P2P verdict deferred: {exc}")
                            time.sleep(5)
                            continue
                    if p2p_node.add_signature(vote):
                        count = len(p2p_node.signatures[traj_hash])
                        required = 3 if weighted_criteria else 2
                        waiting = ("Waiting for per-criterion majority; a third judge may be needed."
                                   if weighted_criteria else "Waiting for second judge.")
                        print(f"[Judge -> Miner] {'PASS' if is_valid else 'FAIL'} vote sent ({count}/{required}). "
                              f"{waiting if count < required else 'Quorum evaluated.'} "
                              f"{error_text if not is_valid else ''}\n")
                    else:
                        print("[Judge] Vote was not accepted; check task/trajectory identity and wallet keys.")
                    
                    time.sleep(2)
                else:
                    time.sleep(5)
                    
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
                ('/engine', 'Install/start Ollama dan siapkan model AI lokal'),
                ('/runtime', 'Siapkan Docker runtime miner/judge (Flask + Chromium)'),
                ('/output', 'Lihat/atur folder hasil task (/output <folder>)'),
                ('/tasks', 'Lihat status task client dan lokasi hasil tersimpan'),
                ('/deploy', 'Auto-deploy Smart Contract ke Localhost'),
                ('/logs', 'Lihat audit log dari tugas sebelumnya'),
                ('/clear', 'Bersihkan layar terminal dan memori percakapan'),
                ('/status', 'Alias untuk /sys (Cek Hardware)'),
                ('/config', 'Konfigurasi Wallet dan Tracker Server'),
                ('/wallet', 'Lihat saldo ZYRA dan alamat Wallet'),
                ('/submit', 'Lempar tugas coding ke jaringan (Mempool)'),
                ('/resolve', 'Cari alias .myth pada registry lokal MNS v0'),
                ('/update', 'Cek dan install update terbaru ZYRA Network'),
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
    from zyra_cmd.client_state import ClientState
    from zyra_cmd.client_tasks import ClientTaskMonitor
    client_state = ClientState(user_data_dir)
    
    print(f"Connected to Wallet: \033[96m{wallet.address}\033[0m")
    
    # Start P2P Node
    print(f"\033[94m[P2P]\033[0m Starting Gossip Node...")
    import threading
    import asyncio
    import random
    from p2p.network import P2PNode
    
    p2p_port = random.randint(5001, 5999)
    p2p_node = P2PNode(port=p2p_port, tracker_url=args.tracker, seed_peer=args.seed_peer)
    p2p_node.on_task_updated = client_state.update_from_network
    client_monitor = ClientTaskMonitor(client_state, p2p_node)
    
    def run_p2p():
        asyncio.run(p2p_node.start())
        
    p2p_thread = threading.Thread(target=run_p2p, daemon=True)
    p2p_thread.start()
    
    from zyra_cmd.installer import check_and_install_ollama, check_and_pull_model
    
    # Auto-Install Ollama Engine if missing
    has_ollama = check_and_install_ollama(state=client_state)
    
    llm = None
    if has_ollama:
        # Check and pull model if needed
        final_model = check_and_pull_model(args.model)
        if final_model:
            args.model = final_model
        
        try:
            llm = LocalLLMGenerator(model_name=args.model)
        except Exception as e:
            print(f"\033[91m[ERROR]\033[0m Failed to connect to Ollama. Make sure Ollama is running.")
            has_ollama = False
        
    history = []
        
    if args.prompt:
        # Single-shot mode
        if llm is None:
            print("[Client] Local AI is unavailable. Run zyra and use /engine to set it up, or /submit to send a task.")
            return
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

        client_monitor.show_tasks(startup=True)
        client_monitor.start()
        
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
                    client_monitor.stop()
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
                    print("  \033[93m/engine\033[0m  - Install/start Ollama and set up a local model")
                    print("  \033[93m/runtime\033[0m - Prepare the shared Docker runtime for mining/judging")
                    print("  \033[93m/submit --web <task>\033[0m - Require a runnable web app and browser checks")
                    print('  \033[93m/submit --spec "acceptance.json" <task>\033[0m - Use your own runtime checks')
                    print("  \033[93m/output\033[0m  - Show result folder; /output <folder> sets it for future tasks")
                    print("  \033[93m/tasks\033[0m   - Show saved client tasks, status, and result locations")
                    print("  \033[93m/resolve <name.myth>\033[0m - Look up a local static .myth alias")
                    print("  \033[93m/export\033[0m  - Save current chat history to a Markdown file")
                    print("  \033[93m/logs\033[0m    - Open the most recent PoUW Swarm Audit Log")
                    print("  \033[93m/judge\033[0m   - Run as P2P Validator Node")
                    print("  \033[93m/link\033[0m    - Link your MetaMask address (e.g., /link 0x...)")
                    print("  \033[93m/claim\033[0m   - Claim ZYRA tokens to your linked MetaMask")
                    print("  \033[93m/stake\033[0m   - Stake ZYRA tokens to become a Validator (requires CELO gas)")
                    print("  \033[93m/update\033[0m  - Cek dan install update terbaru")
                    print("  \033[93mexit\033[0m     - Exit the CLI\n")
                    continue
                elif cmd == '/runtime':
                    try:
                        from ai.execution.runtime import ensure_runtime
                        print(f"[Runtime] Ready: {ensure_runtime()}")
                    except Exception as exc:
                        print(f"[Runtime] {exc}")
                    continue
                elif cmd == '/engine':
                    try:
                        if check_and_install_ollama(state=client_state, force_prompt=True):
                            final_model = check_and_pull_model(args.model)
                            if final_model:
                                args.model = final_model
                            llm = LocalLLMGenerator(model_name=args.model)
                            print(f"[Engine] Ollama siap. Model: {args.model}. Local AI dapat digunakan sekarang.\n")
                    except Exception as e:
                        print(f"[Engine] Setup belum berhasil: {e}. Coba lagi lewat /engine.\n")
                    continue
                elif cmd == '/output' or cmd.startswith('/output '):
                    try:
                        if cmd == '/output':
                            print(f"[Client] Folder hasil: {client_state.get_output_dir()}\n"
                                  'Gunakan /output "D:\\Hasil ZYRA" atau /output ~/hasil-zyra untuk mengubahnya.\n')
                        else:
                            path = client_state.set_output_dir(user_input.split(' ', 1)[1])
                            print(f"[Client] Folder hasil disimpan: {path}\n"
                                  "Berlaku untuk task baru; task sebelumnya tetap memakai folder saat disubmit.\n")
                    except (OSError, ValueError) as e:
                        print(f"[Client] Folder tidak dapat digunakan: {e}\n")
                    continue
                elif cmd == '/tasks':
                    client_monitor.show_tasks()
                    continue
                elif user_input.startswith('/resolve '):
                    from zyra_cmd.mns_v0 import format_result, resolve_name
                    try:
                        name = user_input.split(' ', 1)[1].strip()
                        print(format_result(resolve_name(name)) + "\n")
                    except ValueError as exc:
                        print(f"[MNS v0] {exc}\n")
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
                elif cmd == '/update':
                    print("\033[96m[System]\033[0m Mengecek update terbaru di PyPI...")
                    try:
                        resp = requests.get("https://pypi.org/pypi/zyra-network/json", timeout=10)
                        if resp.status_code == 200:
                            latest_version = resp.json()["info"]["version"]
                            if latest_version != cli_version and cli_version != "dev":
                                print(f"\033[93m[Update Tersedia]\033[0m Versi terbaru: \033[1m{latest_version}\033[0m (Versi lu: {cli_version})")
                                choice = input("Update sekarang dan otomatis restart? [Y/n]: ").strip().lower()
                                if choice != 'n':
                                

                                    if os.name == 'nt':
                                        import tempfile
                                        # Windows: Locked files, need background script
                                        updater_code = f"""import sys, time, subprocess, os
print("Waiting for ZYRA to exit...")
time.sleep(2)
print("Installing update...")
subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "zyra-network"], check=True)
print("Update complete! Restarting ZYRA...")
os.system("start cmd /k zyra")
"""
                                        updater_path = os.path.join(tempfile.gettempdir(), "zyra_updater.py")
                                        with open(updater_path, "w") as f:
                                            f.write(updater_code)
                                            
                                        print("\033[92m[System]\033[0m Memulai proses update. CLI akan tertutup sementara...")
                                        subprocess.Popen([sys.executable, updater_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
                                        sys.exit(0)
                                    else:
                                        # Linux/macOS: Files not locked, upgrade inline and execv
                                        print("\033[92m[System]\033[0m Mendownload dan menginstall update...")
                                        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "zyra-network"], check=True)
                                        print("\033[92m[System]\033[0m Update complete! Restarting ZYRA...")
                                        os.execv(sys.executable, [sys.executable] + sys.argv)
                            else:
                                print(f"\033[92m[System]\033[0m ZYRA CLI lu udah versi paling baru (v{cli_version}).\n")
                        else:
                            print("\033[91m[Error]\033[0m Gagal mengecek update dari PyPI.\n")
                    except Exception as e:
                        print(f"\033[91m[Error]\033[0m {e}\n")
                    continue
                elif cmd == '/judge':
                    run_validator_mode(wallet, llm.model_name if llm else args.model)
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
                    if llm is None:
                        print("[Engine] Use /engine to set up local AI first.\n")
                        continue
                    new_model = user_input.split(' ', 1)[1].strip()
                    if new_model:
                        llm.model_name = new_model
                        print(f"\033[92m[System]\033[0m Model switched to: \033[96m{llm.model_name}\033[0m\n")
                    else:
                        print(f"\033[93m[System]\033[0m Current model is: \033[96m{llm.model_name}\033[0m\n")
                    continue
                elif cmd == '/model':
                    if llm is None:
                        print("[Engine] Use /engine to set up local AI first.\n")
                        continue
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
                    bridge = input("\033[90mEnter Tracker Server URL (default: https://zyra-ai.tail3b049d.ts.net): \033[0m")
                    
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
                elif user_input.startswith('/unstake '):
                    parts = user_input.split(' ', 1)
                    if len(parts) < 2:
                        print("\033[91m[Error]\033[0m Usage: /unstake <amount>\n")
                        continue
                    try:
                        amount = float(parts[1].strip())
                        if amount <= 0:
                            print("\033[91m[Error]\033[0m Amount must be positive.\n")
                            continue
                            
                        print(f"\033[94m[System]\033[0m Initiating Unstaking transaction for {amount} ZYRA...")
                        try:
                            from zyra_cmd.web3_bridge import ZyraWeb3Bridge
                            bridge = ZyraWeb3Bridge()
                            
                            contract_addr = os.environ.get("ZYRA_CONTRACT_ADDRESS")
                            if not contract_addr:
                                print("\033[91m[Error]\033[0m ZYRA_CONTRACT_ADDRESS tidak ditemukan di .env!\n")
                                continue
                                
                            bridge.set_contract_address(contract_addr)
                            tx_hash = bridge.unstake(wallet.private_key, amount)
                            
                            print(f"\033[92m[System]\033[0m Unstaking successful!")
                            print(f"\033[96m[TxHash]\033[0m {tx_hash}\n")
                        except Exception as e:
                            print(f"\033[91m[Web3 Error]\033[0m {e}\n(Pastikan wallet EVM anda memiliki saldo CELO untuk gas)\n")
                    except ValueError:
                        print("\033[91m[Error]\033[0m Invalid amount.\n")
                    continue
                elif user_input.startswith('/automode '):
                    if llm is None:
                        print("\033[91m[Error]\033[0m /automode requires local AI. Use /engine to install/start Ollama.\n")
                        continue
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
                    
                    print(f"\033[93m[Network]\033[0m Mengirim tugas ke P2P Mempool...")
                    try:
                        import uuid
                        import asyncio
                        from p2p.protocol import MessageType, create_message
                        from ai.execution.contract import parse_submission, contract_hash
                        print("[Acceptance] Menganalisis prompt dan menyiapkan checks executable...")
                        task_prompt, acceptance = parse_submission(task_prompt, criterion_generator=llm)
                        print(f"[Acceptance] Sistem menyiapkan {len(acceptance.get('criteria', []))} checks "
                              "otomatis dari prompt sebelum task diklaim.")
                        for criterion in acceptance.get("criteria", []):
                            print(f"  - {criterion['description']} (bobot {criterion['weight']}"
                                  f"{' / wajib lulus' if criterion['hard_gate'] else ''})")
                        
                        task_id = str(uuid.uuid4())
                        acceptance_hash = contract_hash(acceptance)
                        chain_required = os.environ.get("ZYRA_MYTHCHAIN_MODE", "off").lower() == "required"
                        if chain_required:
                            from zyra_cmd.mythchain_adapter import MythchainConfig, MythchainTaskAdapter
                            MythchainTaskAdapter(MythchainConfig.from_env("client")).register_task(
                                task_id, acceptance_hash, criteria=acceptance.get("criteria"))
                        task_payload = {
                            "task_id": task_id,
                            "prompt": task_prompt,
                            "reward": 2.5,
                            "status": "pending",
                            "client": wallet.metamask_address or wallet.address,
                            "acceptance": acceptance,
                            "acceptance_hash": acceptance_hash,
                            "lease_mode": "mythchain" if chain_required else "p2p-advisory"
                        }
                        
                        # Persist before broadcasting; keep local output paths off the network.
                        saved_task = client_state.add_task(task_payload)
                        p2p_node.add_task(task_payload)
                        
                        print(f"\033[92m[Success]\033[0m Tugas berhasil dilempar ke P2P Mempool!")
                        print(f"Task ID: \033[96m{task_id}\033[0m")
                        print(f"Runtime profile: {acceptance['profile']} | entrypoint: {acceptance['entrypoint']}")
                        print(f"Folder hasil: {saved_task['output_dir']}")
                        print("Sekarang tinggal tunggu para Miner di jaringan untuk mengerjakan tugas ini.\n")
                        print("Riwayat tersimpan. Setelah restart, ZYRA akan melanjutkan pemantauan. Cek /tasks.\n")
                    except Exception as e:
                        print(f"\033[91m[Error]\033[0m Gagal submit ke P2P: {e}\n")
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
                    if llm is None:
                        print("\033[91m[Error]\033[0m /mine requires local AI. Use /engine to install/start Ollama.\n")
                        continue
                    print("\n\033[93m[Miner]\033[0m Starting ZYRA Auto-Miner...")
                    print("\033[96m[System]\033[0m Scanning P2P Mempool for new tasks (Press Ctrl+C to stop)...\n")
                    target_wallet = wallet.metamask_address if hasattr(wallet, 'metamask_address') and wallet.metamask_address else wallet.address
                    if not target_wallet: target_wallet = wallet.address
                    
                    try:
                        import time
                        from p2p.protocol import MessageType, create_message
                        import asyncio
                        preferred_task_id = None
                        while True:
                            p2p_node.expire_task_leases()
                            miner_identity = wallet.signing_address or wallet.address
                            claimed = get_pending_miner_task(
                                p2p_node.tasks, preferred_task_id, miner_identity,
                                canonical_mode=os.environ.get("ZYRA_MYTHCHAIN_MODE", "off").lower() == "required")
                            preferred_task_id = None
                            if claimed is None:
                                time.sleep(5)
                                continue

                            task_id, found_task = claimed
                            prompt = found_task.get("prompt")
                            reward = found_task.get("reward", 2.5)

                            canonical_attempt_id = None
                            chain_required = (found_task.get("lease_mode") == "mythchain"
                                              or os.environ.get("ZYRA_MYTHCHAIN_MODE", "off").lower() == "required")
                            if chain_required:
                                try:
                                    chain_config, canonical_lease = claim_mythchain_task(
                                        task_id, found_task.get("acceptance_hash", ""),
                                        criteria=(found_task.get("acceptance") or {}).get("criteria"))
                                except Exception as exc:
                                    print(f"[Mythchain] Canonical claim unavailable; not starting task: {exc}")
                                    time.sleep(5)
                                    continue
                                if canonical_lease is None:
                                    print(f"[Mythchain] Another miner owns task {task_id}; continuing to poll.")
                                    time.sleep(5)
                                    continue
                                canonical_attempt_id = canonical_lease.get(
                                    "attempt_id", canonical_lease.get("attemptId"))
                                print(f"[Mythchain] Canonical lease confirmed: attempt {canonical_attempt_id}")

                            lease = p2p_node.claim_task(task_id, wallet)
                            if lease is None:
                                time.sleep(1)
                                continue
                            # Give concurrent gossip claims a short arbitration window.
                            from p2p.leases import CLAIM_SETTLE_SECONDS
                            time.sleep(CLAIM_SETTLE_SECONDS)
                            p2p_node.expire_task_leases()
                            current_lease = p2p_node.tasks.get(task_id, {}).get("lease", {})
                            if current_lease.get("lease_id") != lease["lease_id"]:
                                print(f"[Miner] Another signed claim won task {task_id}; skipping this attempt.")
                                continue

                            print(f"\n\033[92m[P2P Mempool]\033[0m Found Task! Reward: {reward} ZYRA")
                            print(f"Task ID: \033[96m{task_id}\033[0m")
                            delivered = run_automode(llm, prompt, history, wallet, ledger, llm.model_name, auto_yes=True, planner_model=args.planner_model, coder_model=args.coder_model, task_id=task_id, attempt_id=lease["lease_id"], canonical_attempt_id=canonical_attempt_id)
                            if delivered is False and p2p_node.tasks.get(task_id, {}).get("status") in ("mining", "pending"):
                                print(f"[Miner] Task {task_id} is not submitted yet. Retrying it before polling other tasks.")
                                preferred_task_id = task_id
                                time.sleep(5)
                                continue
                            # After delivery attempt, check what validator decided
                            task_status = p2p_node.tasks.get(task_id, {}).get("status")
                            
                            if task_status == "completed":
                                print(f"\033[92m[Miner]\033[0m Task {task_id} validated successfully! Reward credited.\n")
                            elif task_status == "pending" and p2p_node.tasks[task_id].get("feedback"):
                                # Validator rejected with feedback - retry same task with feedback
                                feedback = p2p_node.tasks[task_id]["feedback"]
                                print(f"\033[93m[Miner]\033[0m Task {task_id} rejected. Feedback: {feedback}\n")
                                print(f"\033[96m[Miner]\033[0m Retrying same task with validator feedback...\n")
                                preferred_task_id = task_id
                                continue
                            elif task_status == "failed":
                                print(f"\033[91m[Miner]\033[0m Task {task_id} permanently failed (no retry). Moving on.\n")
                            else:
                                print(f"\033[93m[Miner]\033[0m Task {task_id} status: {task_status}. Moving on.\n")
                            
                            print("\n\033[96m[System]\033[0m Scanning P2P Mempool for next task...\n")
                            time.sleep(2)
                    except KeyboardInterrupt:
                        print("\n\033[93m[Miner]\033[0m Auto-Miner stopped.\033[0m\n")
                    continue
                
                # If not a slash command, process as AI prompt
                if llm is None:
                    print("\033[91m[Error]\033[0m Use /submit for network tasks, or /engine to set up local AI.\n")
                    continue
                process_prompt(llm, user_input, history, wallet, ledger, llm.model_name)
                
            except KeyboardInterrupt:
                print("\n\033[93mInterrupted. Type 'exit' to quit.\033[0m")
            except EOFError:
                client_monitor.stop()
                break

if __name__ == "__main__":
    main()
