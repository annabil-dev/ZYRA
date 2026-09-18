import os
import json
from flask import Flask, request, jsonify
from web3 import Web3

app = Flask(__name__)

# Hardhat Local Node URL
RPC_URL = "http://127.0.0.1:8545"
web3 = Web3(Web3.HTTPProvider(RPC_URL))

# In a real app, load this from .env (NEVER hardcode in production!)
# This is the hardhat default account #0 private key
ADMIN_PRIVATE_KEY = os.environ.get("PRIVATE_KEY", "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
admin_account = web3.eth.account.from_key(ADMIN_PRIVATE_KEY)

# Contract Address we just deployed
CONTRACT_ADDRESS = "0x5FbDB2315678afecb367f032d93F642f64180aa3"

# Minimal ABI just for the functions we need
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
    }
]''')

zyra_contract = web3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)

@app.route('/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    metamask_address = data.get('metamask_address')
    amount_float = data.get('amount')
    
    if not metamask_address or not amount_float:
        return jsonify({"error": "Missing parameters"}), 400
        
    try:
        # Convert ZYRA amount to Wei (18 decimals)
        amount_wei = web3.to_wei(amount_float, 'ether')
        
        # Build the transaction to call mintReward(to, amount)
        nonce = web3.eth.get_transaction_count(admin_account.address)
        tx = zyra_contract.functions.mintReward(
            web3.to_checksum_address(metamask_address),
            amount_wei
        ).build_transaction({
            'chainId': 31337, # Hardhat local chainId
            'gas': 200000,
            'gasPrice': web3.to_wei('2', 'gwei'),
            'nonce': nonce,
        })
        
        # Sign the transaction with Admin's private key
        signed_tx = web3.eth.account.sign_transaction(tx, private_key=ADMIN_PRIVATE_KEY)
        
        # Broadcast the transaction to the blockchain
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        
        return jsonify({
            "status": "success",
            "message": f"Successfully minted {amount_float} ZYRA to blockchain!",
            "tx_hash": tx_hash.hex()
        }), 200
        
    except Exception as e:
        print(f"Blockchain Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print(f"Bridge Backend Server running on port 5000")
    print(f"Admin Wallet Address: {admin_account.address}")
    app.run(port=5000, debug=True)
