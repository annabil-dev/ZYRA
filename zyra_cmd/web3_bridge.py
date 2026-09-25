import os
import json
from web3 import Web3
from web3.exceptions import ContractLogicError
from dotenv import load_dotenv

# Load .env file from APPDATA or current directory
user_data_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ZYRA AI")
env_path = os.path.join(user_data_dir, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

# Celo Sepolia Testnet RPC
RPC_URL = "https://forno.celo-sepolia.celo-testnet.org"

class ZyraWeb3Bridge:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(RPC_URL))
        
        # Ambil Private Key dari .env
        self.owner_private_key = os.environ.get("PRIVATE_KEY")
        if not self.owner_private_key:
            raise ValueError("PRIVATE_KEY tidak ditemukan di file .env! Harap isi file .env terlebih dahulu.")
            
        # Dapatkan address otomatis dari private key
        account = self.w3.eth.account.from_key(self.owner_private_key)
        self.owner_address = account.address
        
        self.contract_address = None
        self.contract = None
        
        self._load_contract()

    def _load_contract(self):
        # Gunakan hardcoded ABI untuk fungsi mintReward agar tidak perlu membaca file JSON.
        # Ini mengatasi masalah di mana folder blockchain tidak terikut saat dipublish ke PyPI.
        self.abi = [
            {
                "inputs": [
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "amount", "type": "uint256"}
                ],
                "name": "mintReward",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "account", "type": "address"}
                ],
                "name": "balanceOf",
                "outputs": [
                    {"internalType": "uint256", "name": "", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amount", "type": "uint256"}
                ],
                "name": "stake",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amount", "type": "uint256"}
                ],
                "name": "unstake",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "", "type": "address"}
                ],
                "name": "stakedBalances",
                "outputs": [
                    {"internalType": "uint256", "name": "", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]
            
    def set_contract_address(self, address: str):
        self.contract_address = self.w3.to_checksum_address(address)
        self.contract = self.w3.eth.contract(address=self.contract_address, abi=self.abi)

    def get_balance(self, address: str) -> float:
        if not self.w3.is_connected() or not self.contract:
            return 0.0
        addr = self.w3.to_checksum_address(address)
        try:
            bal_wei = self.contract.functions.balanceOf(addr).call()
            return float(self.w3.from_wei(bal_wei, 'ether'))
        except Exception:
            return 0.0

    def mint_reward(self, to_address: str, amount_zyra: float) -> str:
        if not self.w3.is_connected():
            raise ConnectionError("Cannot connect to Celo Sepolia Testnet RPC.")
            
        if not self.contract:
            raise ValueError("Contract address not set. Please deploy or set contract address first.")
            
        to_address = self.w3.to_checksum_address(to_address)
        
        # Convert to Wei (18 decimals)
        amount_wei = self.w3.to_wei(amount_zyra, 'ether')
        
        # Build transaction
        nonce = self.w3.eth.get_transaction_count(self.owner_address)
        
        tx = self.contract.functions.mintReward(to_address, amount_wei).build_transaction({
            'chainId': 11142220, # Celo Sepolia chain ID
            'gas': 200000,
            'gasPrice': self.w3.eth.gas_price,
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
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt.status == 1:
                return self.w3.to_hex(tx_hash)
            else:
                raise Exception("Transaction failed on the blockchain.")
        except ContractLogicError as e:
            raise Exception(f"Smart Contract Logic Error: {e}")
        except Exception as e:
            raise Exception(f"Web3 Error: {e}")

    def stake(self, user_private_key: str, amount_zyra: float) -> str:
        if not self.w3.is_connected():
            raise ConnectionError("Cannot connect to Celo Sepolia Testnet RPC.")
            
        if not self.contract:
            raise ValueError("Contract address not set. Please deploy or set contract address first.")
            
        user_account = self.w3.eth.account.from_key(user_private_key)
        
        # Convert to Wei (18 decimals)
        amount_wei = self.w3.to_wei(amount_zyra, 'ether')
        
        # Build transaction
        nonce = self.w3.eth.get_transaction_count(user_account.address)
        
        tx = self.contract.functions.stake(amount_wei).build_transaction({
            'chainId': 11142220, # Celo Sepolia chain ID
            'gas': 200000,
            'gasPrice': self.w3.eth.gas_price,
            'nonce': nonce,
        })
        
        # Sign transaction
        signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=user_private_key)
        
        # Send transaction
        try:
            raw_tx = getattr(signed_tx, 'raw_transaction', getattr(signed_tx, 'rawTransaction', None))
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt.status == 1:
                return self.w3.to_hex(tx_hash)
            else:
                raise Exception("Transaction failed on the blockchain.")
        except ContractLogicError as e:
            raise Exception(f"Smart Contract Logic Error: {e}")
        except Exception as e:
            raise Exception(f"Web3 Error: {e}")

    def get_staked_balance(self, address: str) -> float:
        if not self.w3.is_connected() or not self.contract:
            return 0.0
        addr = self.w3.to_checksum_address(address)
        try:
            bal_wei = self.contract.functions.stakedBalances(addr).call()
            return float(self.w3.from_wei(bal_wei, 'ether'))
        except Exception:
            return 0.0

    def unstake(self, user_private_key: str, amount_zyra: float) -> str:
        if not self.w3.is_connected():
            raise ConnectionError("Cannot connect to Celo Sepolia Testnet RPC.")
            
        if not self.contract:
            raise ValueError("Contract address not set. Please deploy or set contract address first.")
            
        user_account = self.w3.eth.account.from_key(user_private_key)
        amount_wei = self.w3.to_wei(amount_zyra, 'ether')
        
        nonce = self.w3.eth.get_transaction_count(user_account.address)
        
        tx = self.contract.functions.unstake(amount_wei).build_transaction({
            'chainId': 11142220,
            'gas': 200000,
            'gasPrice': self.w3.eth.gas_price,
            'nonce': nonce,
        })
        
        signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=user_private_key)
        
        try:
            raw_tx = getattr(signed_tx, 'raw_transaction', getattr(signed_tx, 'rawTransaction', None))
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt.status == 1:
                return self.w3.to_hex(tx_hash)
            else:
                raise Exception("Transaction failed on the blockchain.")
        except ContractLogicError as e:
            raise Exception(f"Smart Contract Logic Error: {e}")
        except Exception as e:
            raise Exception(f"Web3 Error: {e}")
