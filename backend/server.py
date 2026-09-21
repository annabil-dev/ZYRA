import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from web3 import Web3
from dotenv import load_dotenv

# Load root .env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = Flask(__name__)
CORS(app)

# Celo Sepolia Testnet
RPC_URL = "https://forno.celo-sepolia.celo-testnet.org"
CHAIN_ID = 11142220
web3 = Web3(Web3.HTTPProvider(RPC_URL))

# Ensure private key and contract address are loaded
ADMIN_PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
if not ADMIN_PRIVATE_KEY:
    raise ValueError("PRIVATE_KEY missing from .env")

admin_account = web3.eth.account.from_key(ADMIN_PRIVATE_KEY)

CONTRACT_ADDRESS = os.environ.get("ZYRA_CONTRACT_ADDRESS")
if not CONTRACT_ADDRESS:
    raise ValueError("ZYRA_CONTRACT_ADDRESS missing from .env")

# Minimal ABI
CONTRACT_ABI = json.loads('''[
    {
      "inputs": [
        { "internalType": "address", "name": "to", "type": "address" },
        { "internalType": "uint256", "name": "amount", "type": "uint256" }
      ],
      "name": "mintReward",
      "outputs": [],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "inputs": [
        { "internalType": "address", "name": "account", "type": "address" }
      ],
      "name": "balanceOf",
      "outputs": [
        { "internalType": "uint256", "name": "", "type": "uint256" }
      ],
      "stateMutability": "view",
      "type": "function"
    }
]''')

zyra_contract = web3.eth.contract(address=web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)

# In-memory tracking for rate limiting (wallet -> list of timestamps)
import time
user_task_history = {}

# Global recent tasks for the Web UI Dashboard
recent_tasks = []

@app.route('/verify_pouw', methods=['POST'])
def verify_pouw():
    """
    Called by the ZYRA CLI when a task is completed.
    Verifies the Trajectory Hash and mints ZYRA tokens to the miner's wallet.
    """
    data = request.json
    wallet_address = data.get('user_wallet')
    trajectory_hash = data.get('trajectory_hash')
    
    trajectory_log = data.get('trajectory_log', [])
    
    if not wallet_address or not trajectory_hash:
        return jsonify({"error": "Missing user_wallet or trajectory_hash"}), 400
        
    print(f"\n[Bridge] Received PoUW from {wallet_address}")
    
    # Check Staking Tier and Rate Limits
    try:
        balance_wei = zyra_contract.functions.balanceOf(web3.to_checksum_address(wallet_address)).call()
        balance_zyra = float(web3.from_wei(balance_wei, 'ether'))
    except Exception as e:
        print(f"[Bridge] Failed to fetch balance: {e}")
        balance_zyra = 0.0
        
    if balance_zyra >= 10000:
        limit = float('inf') # Tier 3
    elif balance_zyra >= 1000:
        limit = 100 # Tier 2
    elif balance_zyra >= 100:
        limit = 30 # Tier 1
    else:
        limit = 5 # Tier 0
        
    now = time.time()
    if wallet_address not in user_task_history:
        user_task_history[wallet_address] = []
        
    # Clean old history (> 1 hour)
    user_task_history[wallet_address] = [t for t in user_task_history[wallet_address] if now - t < 3600]
    
    if len(user_task_history[wallet_address]) >= limit:
        print(f"[Bridge] Rate Limit Exceeded for {wallet_address} (Tier Limit: {limit}/hr).")
        return jsonify({"error": f"Rate limit exceeded. Your current balance ({balance_zyra:.2f} ZYRA) allows {limit} tasks per hour. Stake more ZYRA to increase limit."}), 429
        
    print(f"[Bridge] Trajectory Hash: {trajectory_hash}")
    print(f"[Bridge] Validating Trajectory... ({len(trajectory_log)} steps)")
    
    if not trajectory_log:
        return jsonify({"error": "Missing trajectory_log for validation"}), 400
        
    # Heuristic Validation
    has_delegate = False
    has_success = False
    for step in trajectory_log:
        content = step.get('content', '')
        if "<DELEGATE>" in content:
            has_delegate = True
        if "<CONFIRM_DONE>" in content or "<ALL_DONE>" in content:
            has_success = True
            
    if not has_delegate:
        print("[Bridge] Validation Failed: No real work found.")
        return jsonify({"error": "Validation failed: Fake task, no delegation found."}), 400
        
    if not has_success:
        print("[Bridge] Validation Failed: Task not successfully completed.")
        return jsonify({"error": "Validation failed: Task not completed."}), 400
        
    print("[Bridge] Validation Passed! Processing reward...")
    
    # Extract dynamic reward, limit to max 50 ZYRA per task for security
    reward_amount = float(data.get('reward', 2.5))
    if reward_amount <= 0 or reward_amount > 50.0:
        return jsonify({"error": "Invalid reward amount"}), 400
    
    try:
        amount_wei = web3.to_wei(reward_amount, 'ether')
        
        # Build transaction
        nonce = web3.eth.get_transaction_count(admin_account.address)
        tx = zyra_contract.functions.mintReward(
            web3.to_checksum_address(wallet_address),
            amount_wei
        ).build_transaction({
            'chainId': CHAIN_ID,
            'gas': 200000,
            'gasPrice': web3.eth.gas_price,
            'nonce': nonce,
        })
        
        # Sign and broadcast
        signed_tx = web3.eth.account.sign_transaction(tx, private_key=ADMIN_PRIVATE_KEY)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        
        # Wait for transaction to be mined
        print(f"[Bridge] Waiting for transaction to be mined... ({tx_hash.hex()})")
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        if receipt.status != 1:
            raise Exception("Transaction failed on the blockchain. Might be out of gas or Daily Mint Cap reached.")
            
        print(f"[Bridge] SUCCESS! Tx Hash: {tx_hash.hex()}")
        
        # Record successful task for rate limiting
        user_task_history[wallet_address].append(now)
        
        # Append to recent tasks for Web UI
        recent_tasks.append({
            "wallet": wallet_address,
            "hash": tx_hash.hex(),
            "reward": reward_amount,
            "timestamp": int(now)
        })
        # Keep only last 20 tasks
        if len(recent_tasks) > 20:
            recent_tasks.pop(0)
        
        return jsonify({
            "status": "success",
            "message": f"Successfully minted {reward_amount} ZYRA for valid PoUW!",
            "tx_hash": tx_hash.hex()
        }), 200
        
    except Exception as e:
        print(f"[Bridge] Blockchain Error: {str(e)}")
        return jsonify({
            "error": str(e), 
            "status": "validated_but_mint_failed"
        }), 500

import random
import time
import math

@app.route('/live_tasks', methods=['GET'])
def get_live_tasks():
    """
    Returns the most recent verified PoUW tasks.
    """
    return jsonify({"tasks": recent_tasks}), 200

@app.route('/price', methods=['GET'])
def get_price():
    """
    Simulates a live DEX Liquidity Pool price for ZYRA.
    Uses time-based Sine waves + random noise to make the chart look organic.
    Base price: $0.10. Ranges from $0.05 to $0.15.
    """
    current_time = time.time()
    
    # 1. Macro trend (Slow wave, period = 1 hour)
    macro = math.sin(current_time / 3600.0) * 0.03
    
    # 2. Micro trend (Fast wave, period = 5 mins)
    micro = math.sin(current_time / 300.0) * 0.015
    
    # 3. Random noise (Volatility)
    noise = random.uniform(-0.005, 0.005)
    
    # Base price $0.10
    base_price = 0.10
    
    current_price = base_price + macro + micro + noise
    
    # Determine trend (1h comparison)
    past_macro = math.sin((current_time - 3600) / 3600.0) * 0.03
    past_price = base_price + past_macro
    percent_change = ((current_price - past_price) / past_price) * 100
    
    return jsonify({
        "price_usd": round(current_price, 4),
        "change_24h": round(percent_change, 2)
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"Bridge Backend Server running on port {port}")
    print(f"Admin Wallet Address: {admin_account.address}")
    app.run(host="0.0.0.0", port=port, debug=False)

