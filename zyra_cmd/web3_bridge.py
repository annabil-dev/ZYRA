import os
import json
from web3 import Web3
from web3.exceptions import ContractLogicError

# Default Hardhat local node
RPC_URL = "http://127.0.0.1:8545"

class ZyraWeb3Bridge:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(RPC_URL))
        
        # Hardhat default account #0 (Deployer)
        self.owner_address = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
        self.owner_private_key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        
        self.contract_address = None
        self.contract = None
        
        self._load_contract()

    def _load_contract(self):
        # Cari file ABI hasil kompilasi Hardhat
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        abi_path = os.path.join(base_dir, "blockchain", "artifacts", "contracts", "ZyraToken.sol", "ZyraToken.json")
        
        if not os.path.exists(abi_path):
            raise FileNotFoundError(f"ABI file not found at {abi_path}. Please run 'npx hardhat compile' first.")
            
        with open(abi_path, 'r') as f:
            contract_data = json.load(f)
            self.abi = contract_data['abi']
            
    def set_contract_address(self, address: str):
        self.contract_address = self.w3.to_checksum_address(address)
        self.contract = self.w3.eth.contract(address=self.contract_address, abi=self.abi)

    def mint_reward(self, to_address: str, amount_zyra: float) -> str:
        if not self.w3.is_connected():
            raise ConnectionError("Cannot connect to Web3 RPC (Hardhat Node is probably down).")
            
        if not self.contract:
            raise ValueError("Contract address not set. Please deploy or set contract address first.")
            
        to_address = self.w3.to_checksum_address(to_address)
        
        # Convert to Wei (18 decimals)
        amount_wei = self.w3.to_wei(amount_zyra, 'ether')
        
        # Build transaction
        nonce = self.w3.eth.get_transaction_count(self.owner_address)
        
        tx = self.contract.functions.mintReward(to_address, amount_wei).build_transaction({
            'chainId': 31337, # Hardhat chain ID
            'gas': 200000,
            'maxFeePerGas': self.w3.to_wei('2', 'gwei'),
            'maxPriorityFeePerGas': self.w3.to_wei('1', 'gwei'),
            'nonce': nonce,
        })
        
        # Sign transaction
        signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=self.owner_private_key)
        
        # Send transaction
        try:
            # For Web3.py v6+ we use raw_transaction
            raw_tx = getattr(signed_tx, 'raw_transaction', getattr(signed_tx, 'rawTransaction', None))
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            
            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            if receipt.status == 1:
                return self.w3.to_hex(tx_hash)
            else:
                raise Exception("Transaction failed on the blockchain.")
        except ContractLogicError as e:
            raise Exception(f"Smart Contract Logic Error: {e}")
        except Exception as e:
            raise Exception(f"Web3 Error: {e}")
