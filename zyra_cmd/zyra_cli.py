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
        logo = "\033[96m" + r"""
   _______  _______  ___ 
  /_  /\  \/  / _ \/ _ \ 
   / /  \    /|   / /_\ \
  / /__  |  | | |\ \  _  |
 /____/  |__| |_| \_\/ \_|
""" + "\033[0m"
        print(logo)
        print("\033[1m=========================================\033[0m")
        print("\033[92m    Welcome to ZYRA Interactive CLI\033[0m")
        print("\033[1m=========================================\033[0m")
        print("Type your commands below. Type \033[93mexit\033[0m to quit.\n")
        
        while True:
            try:
                user_input = input("\033[96mZYRA > \033[0m").strip()
                if not user_input:
                    continue
                if user_input.lower() in ['/exit', '/quit', 'exit', 'quit']:
                    print("\033[93mGoodbye! Keep mining ZYRA.\033[0m")
                    break
                    
                process_prompt(llm, user_input, history, wallet, ledger, args.model)
                
            except KeyboardInterrupt:
                print("\n\033[93mInterrupted. Type 'exit' to quit.\033[0m")
            except EOFError:
                break

if __name__ == "__main__":
    main()
