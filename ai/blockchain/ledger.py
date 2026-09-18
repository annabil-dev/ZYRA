import sqlite3
import os
import json
import hashlib
import time

class ZyraLedger:
    """
    A local SQLite-based blockchain ledger for the ZYRA token ecosystem.
    Records Proof of Useful Work (PoUW) minting events and P2P transactions.
    """
    def __init__(self, data_dir: str):
        self.db_path = os.path.join(data_dir, "ledger.db")
        os.makedirs(data_dir, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Blocks Table
        c.execute('''
            CREATE TABLE IF NOT EXISTS blocks (
                height INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                prev_hash TEXT,
                merkle_root TEXT,
                hash TEXT UNIQUE
            )
        ''')
        
        # Transactions Table
        c.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                txid TEXT PRIMARY KEY,
                block_height INTEGER,
                sender TEXT,
                receiver TEXT,
                amount REAL,
                type TEXT, -- 'MINT' (PoUW) or 'TRANSFER'
                signature TEXT,
                timestamp REAL,
                FOREIGN KEY(block_height) REFERENCES blocks(height)
            )
        ''')
        
        # Balances Table (Account based for simplicity in local env)
        c.execute('''
            CREATE TABLE IF NOT EXISTS balances (
                address TEXT PRIMARY KEY,
                balance REAL DEFAULT 0.0
            )
        ''')
        
        conn.commit()
        
        # Create Genesis Block if empty
        c.execute("SELECT COUNT(*) FROM blocks")
        if c.fetchone()[0] == 0:
            self._create_genesis_block(c)
            conn.commit()
            
        conn.close()

    def _create_genesis_block(self, cursor):
        genesis_hash = hashlib.sha256(b"ZYRA_GENESIS_BLOCK").hexdigest()
        cursor.execute('''
            INSERT INTO blocks (timestamp, prev_hash, merkle_root, hash)
            VALUES (?, ?, ?, ?)
        ''', (time.time(), "0"*64, "0"*64, genesis_hash))

    def get_balance(self, address: str) -> float:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT balance FROM balances WHERE address = ?", (address,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else 0.0

    def add_pouw_reward(self, receiver_address: str, amount: float, task_proof: dict) -> str:
        """
        Mints new ZYRA tokens to the receiver for completing a valid AI task.
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        timestamp = time.time()
        
        # Simple Block Generation (1 tx per block for now)
        c.execute("SELECT hash, height FROM blocks ORDER BY height DESC LIMIT 1")
        prev_block = c.fetchone()
        prev_hash = prev_block[0]
        new_height = prev_block[1] + 1
        
        tx_data = f"MINT:{receiver_address}:{amount}:{timestamp}:{json.dumps(task_proof)}"
        txid = hashlib.sha256(tx_data.encode()).hexdigest()
        
        # Create Block
        block_hash = hashlib.sha256(f"{new_height}{timestamp}{prev_hash}{txid}".encode()).hexdigest()
        c.execute('''
            INSERT INTO blocks (height, timestamp, prev_hash, merkle_root, hash)
            VALUES (?, ?, ?, ?, ?)
        ''', (new_height, timestamp, prev_hash, txid, block_hash))
        
        # Insert Transaction
        c.execute('''
            INSERT INTO transactions (txid, block_height, sender, receiver, amount, type, signature, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (txid, new_height, "SYSTEM", receiver_address, amount, "MINT", "POUW_VALIDATED", timestamp))
        
        # Update Balance
        c.execute("INSERT OR IGNORE INTO balances (address, balance) VALUES (?, 0.0)", (receiver_address,))
        c.execute("UPDATE balances SET balance = balance + ? WHERE address = ?", (amount, receiver_address))
        
        conn.commit()
        conn.close()
        return txid

    def get_recent_transactions(self, limit=10):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            SELECT txid, type, amount, receiver, timestamp 
            FROM transactions 
            ORDER BY timestamp DESC LIMIT ?
        ''', (limit,))
        rows = c.fetchall()
        conn.close()
        
        result = []
        for r in rows:
            result.append({
                "txid": r[0],
                "type": r[1],
                "amount": r[2],
                "receiver": r[3],
                "timestamp": r[4]
            })
        return result
