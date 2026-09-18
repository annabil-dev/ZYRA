import os
import sys
import time
import json
import argparse
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.inference.local_llm_client import LocalLLMGenerator
from ai.blockchain.wallet import ZyraWallet
from ai.blockchain.ledger import ZyraLedger
from ai.blockchain.pouw_validator import PoUWValidator

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
            temperature=0.7,
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
        
    except Exception as e:
        print(f"\n\033[91m[ERROR]\033[0m {str(e)}")
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


def main():
    parser = argparse.ArgumentParser(description="ZYRA Developer CLI - Agentic AI + PoUW Mining")
    parser.add_argument("prompt", type=str, nargs='?', help="The prompt or task for ZYRA AI (Optional)")
    parser.add_argument("--model", type=str, default="llama3.1:8b", help="Ollama model to use")
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
        
        while True:
            try:
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
                    print("  \033[93m/export\033[0m  - Save current chat history to a Markdown file")
                    print("  \033[93m/link\033[0m    - Link your MetaMask address (e.g., /link 0x...)")
                    print("  \033[93m/claim\033[0m   - Claim ZYRA tokens to your linked MetaMask")
                    print("  \033[93mexit\033[0m     - Exit the CLI\n")
                    continue
                elif cmd in ['/wallet', '/balance']:
                    balance = ledger.get_balance(wallet.address)
                    print(f"\n\033[1m[Wallet Info]\033[0m")
                    print(f"Address: \033[96m{wallet.address}\033[0m")
                    if wallet.metamask_address:
                        print(f"Linked Web3: \033[95m{wallet.metamask_address}\033[0m")
                    print(f"Balance: \033[92m{balance:.4f} ZYRA\033[0m\n")
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
                            
                            # Hardcoded default contract address for Hardhat account 0 first deployment
                            bridge.set_contract_address("0x5FbDB2315678afecb367f032d93F642f64180aa3")
                            
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
                
                # If not a slash command, process as AI prompt
                process_prompt(llm, user_input, history, wallet, ledger, llm.model_name)
                
            except KeyboardInterrupt:
                print("\n\033[93mInterrupted. Type 'exit' to quit.\033[0m")
            except EOFError:
                break

if __name__ == "__main__":
    main()
