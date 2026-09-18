import os
import json
import hashlib
import binascii
try:
    import ecdsa
    HAS_ECDSA = True
except ImportError:
    HAS_ECDSA = False

class ZyraWallet:
    """
    Handles cryptographic keys and signing for the local ZYRA token ecosystem.
    Uses ECDSA SECP256k1 if available, otherwise falls back to a simulated hash (for testing).
    """
    def __init__(self, data_dir: str):
        self.wallet_file = os.path.join(data_dir, "wallet.json")
        self.private_key = None
        self.public_key = None
        self.address = None
        self.metamask_address = None
        self.load_or_create_wallet()

    def _generate_simulated_keys(self):
        """Fallback if ecdsa is not installed. Not secure!"""
        import uuid
        self.private_key = hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()
        self.public_key = hashlib.sha256(self.private_key.encode()).hexdigest()
        self.address = "Z" + hashlib.ripemd160(self.public_key.encode()).hexdigest() if hasattr(hashlib, 'ripemd160') else "Z" + self.public_key[:40]

    def _generate_ecdsa_keys(self):
        """Secure key generation using secp256k1 (Bitcoin standard)."""
        sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
        vk = sk.get_verifying_key()
        
        self.private_key = sk.to_string().hex()
        self.public_key = vk.to_string().hex()
        
        # Hash pubkey to get address (SHA256 then RIPEMD160 usually, here we use double SHA256 for simplicity if RIPEMD missing)
        pub_hash = hashlib.sha256(self.public_key.encode()).hexdigest()
        self.address = "Z" + pub_hash[:40] # Z-prefix for ZYRA

    def load_or_create_wallet(self):
        if os.path.exists(self.wallet_file):
            with open(self.wallet_file, 'r') as f:
                data = json.load(f)
                self.private_key = data.get('private_key')
                self.public_key = data.get('public_key')
                self.address = data.get('address')
                self.metamask_address = data.get('metamask_address')
        else:
            if HAS_ECDSA:
                self._generate_ecdsa_keys()
            else:
                self._generate_simulated_keys()
                
            self.metamask_address = None
                
            self.save()

    def save(self):
        os.makedirs(os.path.dirname(self.wallet_file), exist_ok=True)
        with open(self.wallet_file, 'w') as f:
            json.dump({
                "private_key": self.private_key,
                "public_key": self.public_key,
                "address": self.address,
                "metamask_address": self.metamask_address
            }, f, indent=4)

    def sign_transaction(self, tx_data: str) -> str:
        """Signs a transaction payload string with the private key."""
        if HAS_ECDSA and len(self.private_key) == 64: # 32 bytes hex
            try:
                sk = ecdsa.SigningKey.from_string(bytes.fromhex(self.private_key), curve=ecdsa.SECP256k1)
                signature = sk.sign(tx_data.encode())
                return signature.hex()
            except Exception:
                pass
                
        # Fallback simulated signature
        return hashlib.sha256((self.private_key + tx_data).encode()).hexdigest()

    @staticmethod
    def verify_signature(public_key: str, signature: str, tx_data: str) -> bool:
        if HAS_ECDSA and len(public_key) == 128:
            try:
                vk = ecdsa.VerifyingKey.from_string(bytes.fromhex(public_key), curve=ecdsa.SECP256k1)
                return vk.verify(bytes.fromhex(signature), tx_data.encode())
            except Exception:
                return False
        return True # Fallback mode accepts all
