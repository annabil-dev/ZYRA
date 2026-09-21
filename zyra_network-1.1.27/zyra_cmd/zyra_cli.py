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

from ai.inference.local_llm_client import LocalLLMGenerator
from ai.blockchain.wallet import ZyraWallet
from ai.blockchain.ledger import ZyraLedger
from ai.blockchain.pouw_validator import PoUWValidator

BRIDGE_URL = os.environ.get("ZYRA_BRIDGE_URL", "https://kccmy-114-10-44-157.free.pinggy.net")

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
    
    proof = PoUWValidator.generate_proof(
        task_type="AGENT_EXECUTION" if is_tool_call else "TEXT_GEN",
        prompt=prompt,
        tokens=total_tokens,
        metrics={"latency_ms": latency_ms, "vram_mb": 0.0},
        wallet_address=wallet.address
    )
    
    reward = proof.get('reward', 0.0)
    if reward > 0:
        ledger.add_pouw_reward(wallet.address, reward, proof)
        print(f"\033[92m[SUCCESS]\033[0m You earned \033[1m+{reward:.4f} ZYRA\033[0m for this terminal task!\n")
    else:
        print("\033[91m[REJECTED]\033[0m Task did not qualify for PoUW rewards.\n")


def run_automode(llm, initial_task: str, history: list, wallet: ZyraWallet, ledger: ZyraLedger, model_name: str, auto_yes: bool = False, planner_model: str = None, coder_model: str = None):
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
5. ZERO-TRUST POLICY: If you ask the Coder to verify something, demand to see the STDOUT output. If they provided the STDOUT and it proves success, DO NOT ask them to verify it again. Proceed to the next step or finish.
6. DO NOT output <ALL_DONE> until you have verified all steps are truly finished.
7. When the entire task is truly finished, output exactly:
<ALL_DONE>
8. If the system asks you to confirm completion, and you are 100% sure, reply exactly:
<CONFIRM_DONE>"""
    planner_history.append({"role": "user", "content": planner_sys})
    
    coder_sys = """You are the CODER AGENT running on WINDOWS POWERSHELL.
You will receive instructions from the PLANNER.
RULES:
1. You are on Windows. DO NOT use Linux commands like `apt-get` or `bash`. Use PowerShell equivalents.
2. IMPORTANT WINDOWS PATH RULE: When writing Python code, ALWAYS use raw strings for Windows paths (e.g. `r"C:\path"`) or forward slashes (e.g. `"C:/path"`) to avoid SyntaxWarning \\S escape sequence errors!
3. To execute a command, output it exactly like this:
<CMD>your command</CMD>
4. If you need to CREATE or WRITE a Python script, you MUST create the file first using PowerShell inside a <CMD> tag. For example:
<CMD>
$code = @"
print(r'D:\\Hello')
"@
Set-Content -Path "script.py" -Value $code
</CMD>
NEVER try to run `python script.py` before you have actually created it!
5. You can output MULTIPLE <CMD> tags per turn to run commands sequentially.
6. ANTI-LAZINESS POLICY: If the Planner asks you to VERIFY or CHECK a file/result, you MUST execute a command (like `Test-Path`, `cat`, or running a script) in the SAME turn. You CANNOT just output [STEP_COMPLETE] without providing terminal output proof.
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
        
        if "<CONFIRM_DONE>" in planner_output:
            print(f"\033[92m[Multi-Agent Swarm]\033[0m Task completed and confirmed successfully!\n")
            break

        if "<ALL_DONE>" in planner_output:
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
            
        delegate_matches = re.findall(r"<DELEGATE>(.*?)(?:</DELEGATE>|$)", planner_output, re.DOTALL)
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
        
        coder_steps = 5
        step_completed = False
        for step in range(coder_steps):
            # Prevent Context Overflow for Coder (Keep System Prompt + last 9 messages)
            if len(coder_history) > 10:
                coder_history = [coder_history[0]] + coder_history[-9:]
                
            coder_output = generate_response(coder_history, "Coder")
            coder_history.append({"role": "assistant", "content": coder_output})
            full_trajectory_log.append({"role": "coder", "content": coder_output})
            
            cmd_matches = re.findall(r"<CMD>(.*?)(?:</CMD>|$)", coder_output, re.DOTALL)
            
            if cmd_matches:
                all_success = True
                for command in cmd_matches:
                    command = command.strip()
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
                            
                    print(f"\033[92m[System]\033[0m Executing...")
                    try:
                        if os.name == 'nt':
                            result = subprocess.run(["powershell", "-Command", command], capture_output=True, text=True, timeout=60)
                        else:
                            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
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
                        
                        if "No such file or directory" in stderr:
                            coder_history.append({"role": "user", "content": f"Command '{command}' failed:\n{stderr}\n\nSYSTEM WARNING: The file does not exist! You MUST create it first using `Set-Content` inside <CMD> tags. Stop trying to run a file that doesn't exist."})
                        else:
                            coder_history.append({"role": "user", "content": f"Command '{command}' output:\n{output_msg}"})
                        
                        if result.returncode != 0:
                            all_success = False
                            break # Stop executing further commands if one fails
                            
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
                
                # If they included [STEP_COMPLETE] in the same message, process it if commands succeeded
                if "[STEP_COMPLETE]" in coder_output and all_success:
                    print(f"\033[93m[Coder Agent]\033[0m Step reported as complete.\n")
                    planner_history.append({"role": "user", "content": "CODER REPORT: Step completed successfully."})
                    step_completed = True
                    successful_delegations += 1
                    break
                    
            elif "[STEP_COMPLETE]" in coder_output:
                print(f"\033[93m[Coder Agent]\033[0m Step reported as complete.\n")
                planner_history.append({"role": "user", "content": "CODER REPORT: Step completed successfully."})
                step_completed = True
                successful_delegations += 1
                break
            else:
                coder_history.append({"role": "user", "content": "Use <CMD> to execute or [STEP_COMPLETE] if done."})
                
        if not step_completed:
            planner_history.append({"role": "user", "content": "CODER REPORT: Coder reached max steps without completing the task."})
    else:
        print(f"\033[93m[Multi-Agent Swarm]\033[0m Reached maximum cycles. Stopping.\n")

    # Reward for automode
    print("\033[93m[PoUW Validator]\033[0m Submitting Proof of Useful Work to ZYRA Bridge Server...")
    proof = PoUWValidator.generate_proof(
        task_type="AGENT_EXECUTION",
        prompt=initial_task,
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
        response = requests.post(f"{BRIDGE_URL}/verify_pouw", json={
            "user_wallet": target_wallet,
            "trajectory_hash": proof.get('proof_hash', '0x0000'),
            "reward": reward,
            "trajectory_log": full_trajectory_log
        }, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            tx_hash = data.get("tx_hash", "Unknown")
            print(f"\033[92m[SUCCESS]\033[0m Task verified by Bridge! \033[1m+{reward:.4f} ZYRA\033[0m sent to wallet.")
            print(f"Transaction Hash: \033[96m{tx_hash}\033[0m\n")
            
            # Save local copy for /wallet history
            ledger.add_pouw_reward(target_wallet, reward, proof)
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
                ('/automode', 'Aktifkan Swarm AI Multi-Model (/automode <task>)'),
                ('/models', 'Buka pengelola model lokal Ollama'),
                ('/deploy', 'Auto-deploy Smart Contract ke Localhost'),
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
    parser = argparse.ArgumentParser(description="ZYRA Developer CLI - Agentic AI + PoUW Mining")
    parser.add_argument("prompt", type=str, nargs='?', help="The prompt or task for ZYRA AI (Optional)")
    parser.add_argument("--model", type=str, default="llama3.1:8b", help="Default Ollama model to use")
    parser.add_argument("--planner-model", type=str, default=None, help="Specific model for the Planner Agent")
    parser.add_argument("--coder-model", type=str, default=None, help="Specific model for the Coder Agent")
    args = parser.parse_args()

    print(f"\033[92m[ZYRA CLI]\033[0m Starting Local Agentic AI...")
    
    # Initialize Core Components
    user_data_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ZYRA AI")
    wallet = ZyraWallet(user_data_dir)
    ledger = ZyraLedger(user_data_dir)
    
    print(f"Connected to Wallet: \033[96m{wallet.address}\033[0m")
    
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
        print(f"\033[92m    Welcome to ZYRA Interactive CLI \033[90m(v{cli_version})\033[0m")
        print("\033[1m=================================================\033[0m")
        print("Type your commands below. Type \033[93m/help\033[0m for available commands, or \033[93mexit\033[0m to quit.\n")
        
        if PromptSession:
            session = PromptSession(completer=ZyraCommandCompleter(), style=zyra_style)
        else:
            session = None
            print("\033[93m[System] Tip: Install prompt_toolkit for interactive autocomplete dropdowns!\033[0m\n")
        
        while True:
            try:
                if session:
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
                    print("  \033[93m/clear\033[0m   - Clear terminal screen and conversation history")
                    print("  \033[93m/model\033[0m   - Change active LLM model (e.g., /model llama3.2)")
                    print("  \033[93m/sys\033[0m     - Monitor hardware (CPU & RAM usage)")
                    print("  \033[93m/read\033[0m    - Read a local file (e.g., /read script.py)")
                    print("  \033[93m/search\033[0m  - Live web search (e.g., /search latest news)")
                    print("  \033[93m/automode\033[0m- Autonomous Coding Agent (e.g., /automode create a react app)")
                    print("  \033[93m/export\033[0m  - Save current chat history to a Markdown file")
                    print("  \033[93m/logs\033[0m    - Open the most recent PoUW Swarm Audit Log")
                    print("  \033[93m/link\033[0m    - Link your MetaMask address (e.g., /link 0x...)")
                    print("  \033[93m/claim\033[0m   - Claim ZYRA tokens to your linked MetaMask")
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
                elif user_input == 'zyra config':
                    print("\033[94m[ZYRA Config]\033[0m")
                    model = input("\033[90mSelect Local Planner Model (e.g. llama3.1:8b): \033[0m")
                    addr = input("\033[90mEnter EVM Wallet Address: \033[0m")
                    print(f"\033[92m✓ Configuration securely saved to .env\033[0m\n")
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
                        print("  2. \033[96mllama3.3:70b\033[0m    - [Heavy] The ultimate Llama (Requires 64GB+ RAM)")
                        print("  3. \033[96mqwen2.5-coder:7b\033[0m - [Coding] The best small model for code generation")
                        print("  4. \033[96mphi4\033[0m             - [Balanced] Microsoft's latest compact but smart model")
                        print("  5. \033[95mCustom (Type your own model name from ollama.com)\033[0m")
                        
                        choices = {'1': 'deepseek-r1:7b', '2': 'llama3.3', '3': 'qwen2.5-coder:7b', '4': 'phi4'}
                        ans = input("\n\033[93mEnter number (1-5): \033[0m").strip()
                        
                        target_model = None
                        if ans in choices:
                            target_model = choices[ans]
                        elif ans == '5':
                            target_model = input("\033[93mEnter exact model name: \033[0m").strip()
                            
                        if target_model:
                            print(f"\n\033[94m[System]\033[0m Pulling {target_model} from Ollama registry...")
                            try:
                                process = subprocess.Popen(["ollama", "pull", target_model], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                                for line in process.stdout:
                                    sys.stdout.write("\033[96m" + line + "\033[0m")
                                    sys.stdout.flush()
                                process.wait()
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
                
                # If not a slash command, process as AI prompt
                process_prompt(llm, user_input, history, wallet, ledger, llm.model_name)
                
            except KeyboardInterrupt:
                print("\n\033[93mInterrupted. Type 'exit' to quit.\033[0m")
            except EOFError:
                break

if __name__ == "__main__":
    main()
