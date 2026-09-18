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

def main():
    parser = argparse.ArgumentParser(description="ZYRA Developer CLI - Agentic AI + PoUW Mining")
    parser.add_argument("prompt", type=str, help="The prompt or task for ZYRA AI")
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
        
    # Simple security auto-approve for CLI
    def cli_security_callback(tool_name, arguments_dict):
        print(f"\n\033[93m[AGENT ACTION]\033[0m Executing \033[96m{tool_name}\033[0m...")
        return True # Auto approve in CLI for developers
        
    print("\n\033[94mZYRA is thinking...\033[0m\n")
    
    start_time = time.time()
    total_tokens = 0
    final_text = ""
    is_tool_call = False
    
    try:
        # Stream the response
        for text, delta, metrics in llm.generate(
            prompt=args.prompt,
            history=[],
            max_tokens=4096,
            temperature=0.7,
            top_k=40,
            top_p=0.9,
            security_callback=cli_security_callback
        ):
            if "tool_calls" in text:
                is_tool_call = True
            
            # Print delta
            sys.stdout.write(delta)
            sys.stdout.flush()
            total_tokens += 1
            final_text = text
            
        print("\n")
        
    except Exception as e:
        print(f"\n\033[91m[ERROR]\033[0m {str(e)}")
        sys.exit(1)
        
    end_time = time.time()
    latency_ms = (end_time - start_time) * 1000
    
    # --- PoUW MINING LOGIC ---
    print("\033[93m[PoUW Validator]\033[0m Submitting Proof of Useful Work...")
    
    difficulty = 2 if is_tool_call else 1
    
    proof = PoUWValidator.generate_proof(
        wallet_address=wallet.address,
        task_type="CLI_TEXT_GEN",
        compute_time_ms=latency_ms,
        tokens_generated=total_tokens,
        model_name=args.model,
        difficulty=difficulty,
        energy_joules=latency_ms * 0.05
    )
    
    if PoUWValidator.verify_proof(proof):
        reward = proof['reward_zyra']
        ledger.add_transaction(wallet.address, reward, "MINT", proof['proof_hash'])
        print(f"\033[92m[SUCCESS]\033[0m You earned \033[1m+{reward:.4f} ZYRA\033[0m for this terminal task!")
    else:
        print("\033[91m[REJECTED]\033[0m Invalid PoUW signature.")
        
if __name__ == "__main__":
    main()
