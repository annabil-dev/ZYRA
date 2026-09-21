import os
from web3 import Web3
from dotenv import load_dotenv

load_dotenv("D:/Semester 5/AI/my_ai/.env")

RPC_URL = "https://forno.celo-sepolia.celo-testnet.org"
web3 = Web3(Web3.HTTPProvider(RPC_URL))

contract_address = web3.to_checksum_address(os.environ["ZYRA_CONTRACT_ADDRESS"])
pk = os.environ["PRIVATE_KEY"]
account = web3.eth.account.from_key(pk)

abi = [{"inputs":[],"name":"owner","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},
       {"inputs":[],"name":"dailyMinted","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]

contract = web3.eth.contract(address=contract_address, abi=abi)

print(f"My Address: {account.address}")
try:
    owner = contract.functions.owner().call()
    print(f"Contract Owner: {owner}")
    print(f"Is Owner? {account.address == owner}")
    
    daily = contract.functions.dailyMinted().call()
    print(f"Daily Minted: {web3.from_wei(daily, 'ether')} ZYRA")
    
    celo_balance = web3.eth.get_balance(account.address)
    print(f"My CELO Balance: {web3.from_wei(celo_balance, 'ether')} CELO")
except Exception as e:
    print(f"Error querying contract: {e}")
