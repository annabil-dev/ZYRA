import os
import json
import time
import sqlite3
import uuid
import requests
import urllib.request
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from web3 import Web3
from dotenv import load_dotenv

# Load root .env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = Flask(__name__, template_folder='templates', static_folder='static')
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
user_task_history = {}

# Global recent tasks for the Web UI Dashboard
recent_tasks = []

# Initialize SQLite Database for Task Pool
DB_FILE = os.path.join(os.path.dirname(__file__), "zyra_tasks.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            prompt TEXT NOT NULL,
            reward REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at REAL NOT NULL,
            completed_by TEXT,
            completed_at REAL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS pending_validations (
            id TEXT PRIMARY KEY,
            wallet TEXT NOT NULL,
            trajectory_hash TEXT NOT NULL,
            reward REAL NOT NULL,
            trajectory_log TEXT NOT NULL,
            task_id TEXT,
            created_at REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# P2P Bootstrap Tracker
registered_peers = set()

@app.route('/register_peer', methods=['POST'])
def register_peer():
    data = request.json
    ws_url = data.get('ws_url')
    if ws_url:
        registered_peers.add(ws_url)
    return jsonify({"peers": list(registered_peers)}), 200

@app.route('/client/submit_task', methods=['POST'])
def submit_task():
    """Client submits a task to the ZYRA network"""
    data = request.json
    prompt = data.get('prompt')
    reward = data.get('reward', 2.5) # Default 2.5 ZYRA
    
    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400
        
    task_id = str(uuid.uuid4())
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO tasks (id, prompt, reward, status, created_at) VALUES (?, ?, ?, ?, ?)',
              (task_id, prompt, reward, 'pending', time.time()))
    conn.commit()
    conn.close()
    
    return jsonify({
        "message": "Task submitted to the pool successfully",
        "task_id": task_id,
        "reward": reward
    }), 201

@app.route('/miner/get_task', methods=['GET'])
def get_task():
    """Miner requests a task from the network"""
    wallet = request.args.get('wallet')
    if not wallet:
        return jsonify({"error": "Wallet address required"}), 400
        
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Get the oldest pending task
    c.execute('SELECT * FROM tasks WHERE status = "pending" ORDER BY created_at ASC LIMIT 1')
    task = c.fetchone()
    
    if not task:
        conn.close()
        return jsonify({"message": "No tasks available"}), 404
        
    # Mark as processing (using wallet to lock it temporarily if we wanted to, but for now just status change)
    # Actually for MVP, let's just leave it as 'pending' until they complete it, or mark it processing
    c.execute('UPDATE tasks SET status = "processing" WHERE id = ?', (task['id'],))
    conn.commit()
    conn.close()
    
    return jsonify({
        "task_id": task['id'],
        "prompt": task['prompt'],
        "reward": task['reward']
    }), 200

@app.route('/submit_pouw', methods=['POST'])
def submit_pouw():
    """
    Called by the ZYRA CLI when a task is completed (Miner).
    Checks rate limits, then adds the Trajectory to the Mempool for P2P Validation.
    """
    data = request.json
    wallet_address = data.get('user_wallet')
    trajectory_hash = data.get('trajectory_hash')
    task_id = data.get('task_id')
    reward_amount = float(data.get('reward', 2.5))
    trajectory_log = data.get('trajectory_log', [])
    
    if not wallet_address or not trajectory_hash or not trajectory_log:
        return jsonify({"error": "Missing required data"}), 400
        
    print(f"\n[Mempool] Received PoUW submission from {wallet_address}")
    
    # Check Staking Tier and Rate Limits (to prevent spamming the mempool)
    try:
        balance_wei = zyra_contract.functions.balanceOf(web3.to_checksum_address(wallet_address)).call()
        balance_zyra = float(web3.from_wei(balance_wei, 'ether'))
    except Exception as e:
        print(f"[Mempool] Failed to fetch balance: {e}")
        balance_zyra = 0.0
        
    if balance_zyra >= 10000:
        limit = float('inf')
    elif balance_zyra >= 1000:
        limit = 100
    elif balance_zyra >= 100:
        limit = 30
    else:
        limit = 5
        
    now = time.time()
    if wallet_address not in user_task_history:
        user_task_history[wallet_address] = []
        
    user_task_history[wallet_address] = [t for t in user_task_history[wallet_address] if now - t < 3600]
    
    if len(user_task_history[wallet_address]) >= limit:
        print(f"[Mempool] Rate Limit Exceeded for {wallet_address}")
        return jsonify({"error": f"Rate limit exceeded. Balance: {balance_zyra:.2f} ZYRA. Limit: {limit}/hr."}), 429
        
    if reward_amount <= 0 or reward_amount > 50.0:
        return jsonify({"error": "Invalid reward amount"}), 400

    # Add to SQLite Mempool
    validation_id = str(uuid.uuid4())
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO pending_validations (id, wallet, trajectory_hash, reward, trajectory_log, task_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
              (validation_id, wallet_address, trajectory_hash, reward_amount, json.dumps(trajectory_log), task_id, now))
    conn.commit()
    conn.close()

    print(f"[Mempool] Task added to validation queue! ID: {validation_id}")
    return jsonify({
        "status": "pending_validation",
        "message": "Task submitted to mempool. Awaiting P2P Validator.",
        "validation_id": validation_id
    }), 200

@app.route('/api/ipfs/upload', methods=['POST'])
def upload_ipfs_endpoint():
    """Allows Miners to upload trajectories to IPFS using the Server's Pinata API keys"""
    data = request.json
    if not data or 'trajectory' not in data:
        return jsonify({"error": "Missing trajectory data"}), 400
        
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from app.utils.ipfs import upload_to_ipfs
        
        cid = upload_to_ipfs(data['trajectory'])
        if cid:
            print(f"[IPFS] Successfully pinned trajectory. CID: {cid}")
            return jsonify({"cid": cid}), 200
        else:
            print(f"[IPFS] Failed to pin trajectory.")
            return jsonify({"error": "IPFS upload failed internally"}), 500
    except Exception as e:
        print(f"[IPFS ERROR] {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/validator/get_task', methods=['GET'])
def get_validation_task():
    """Validator requests a pending PoUW task to judge"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Get the oldest pending validation
    c.execute('SELECT * FROM pending_validations ORDER BY created_at ASC LIMIT 1')
    task = c.fetchone()
    conn.close()
    
    if not task:
        return jsonify({"message": "No tasks available"}), 404
        
    return jsonify({
        "validation_id": task['id'],
        "wallet": task['wallet'],
        "trajectory_hash": task['trajectory_hash'],
        "reward": task['reward'],
        "trajectory_log": json.loads(task['trajectory_log']),
        "task_id": task['task_id']
    }), 200

@app.route('/validator/submit_verdict', methods=['POST'])
def submit_verdict():
    """Validator submits the verdict for a task. If valid, Bridge mints the reward for the Miner."""
    data = request.json
    validation_id = data.get('validation_id')
    validator_wallet = data.get('validator_wallet')
    is_valid = data.get('is_valid')
    reason = data.get('reason', '')
    
    if not validation_id or validator_wallet is None or is_valid is None:
        return jsonify({"error": "Missing required data"}), 400
        
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM pending_validations WHERE id = ?', (validation_id,))
    task = c.fetchone()
    
    if not task:
        conn.close()
        return jsonify({"error": "Task not found in mempool"}), 404
        
    print(f"\n[Relayer] Received verdict from {validator_wallet} for validation {validation_id}: {'VALID' if is_valid else 'INVALID'}")
    
    if not is_valid:
        # Task is rejected by network. Delete from mempool.
        c.execute('DELETE FROM pending_validations WHERE id = ?', (validation_id,))
        conn.commit()
        conn.close()
        print(f"[Relayer] Task rejected. Deleted from mempool.")
        return jsonify({"status": "rejected", "message": "Verdict accepted (Invalid)."}), 200

    # Task is VALID. Delete from mempool and MINT to MINER!
    miner_wallet = task['wallet']
    reward_amount = task['reward']
    task_id = task['task_id']
    
    c.execute('DELETE FROM pending_validations WHERE id = ?', (validation_id,))
    conn.commit()
    conn.close()
    
    print(f"[Relayer] Consensus Reached! Minting {reward_amount} ZYRA to Miner: {miner_wallet}")
    
    try:
        amount_wei = web3.to_wei(reward_amount, 'ether')
        nonce = web3.eth.get_transaction_count(admin_account.address)
        tx = zyra_contract.functions.mintReward(
            web3.to_checksum_address(miner_wallet),
            amount_wei
        ).build_transaction({
            'chainId': CHAIN_ID,
            'gas': 200000,
            'gasPrice': web3.eth.gas_price,
            'nonce': nonce,
        })
        
        signed_tx = web3.eth.account.sign_transaction(tx, private_key=ADMIN_PRIVATE_KEY)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        
        print(f"[Relayer] Waiting for transaction to be mined... ({tx_hash.hex()})")
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        if receipt.status != 1:
            raise Exception("Transaction failed on the blockchain.")
            
        print(f"[Relayer] SUCCESS! Tx Hash: {tx_hash.hex()}")
        
        if task_id:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('UPDATE tasks SET status = "completed", completed_by = ?, completed_at = ? WHERE id = ?',
                      (miner_wallet, time.time(), task_id))
            conn.commit()
            conn.close()
            
        now = time.time()
        if miner_wallet not in user_task_history:
            user_task_history[miner_wallet] = []
        user_task_history[miner_wallet].append(now)
        
        recent_tasks.append({
            "wallet": miner_wallet,
            "hash": tx_hash.hex(),
            "reward": reward_amount,
            "timestamp": int(now)
        })
        if len(recent_tasks) > 20:
            recent_tasks.pop(0)
            
        return jsonify({
            "status": "success",
            "message": f"Successfully minted reward to {miner_wallet}!",
            "tx_hash": tx_hash.hex()
        }), 200
        
    except Exception as e:
        print(f"[Relayer] Blockchain Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

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

@app.route('/api/mempool', methods=['GET'])
def api_mempool():
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT wallet, trajectory_hash, reward, created_at FROM pending_validations ORDER BY created_at DESC LIMIT 20')
        rows = c.fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/network_stats', methods=['GET'])
def network_stats():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM pending_validations')
        mempool_size = c.fetchone()[0]
        conn.close()
        return jsonify({
            "active_nodes": len(registered_peers) + 1,  # +1 for the tracker itself
            "mempool_size": mempool_size
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"Bridge Backend Server running on port {port}")
    print(f"Admin Wallet Address: {admin_account.address}")
    app.run(host="0.0.0.0", port=port, debug=False)

