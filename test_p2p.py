import asyncio
import threading
import time
from p2p.network import P2PNode

def run_node1():
    n1 = P2PNode(port=5001)
    asyncio.run(n1.start())

def run_node2():
    n2 = P2PNode(port=5002)
    # Give it a tiny moment to let node1 start
    time.sleep(1)
    n2.add_trajectory({"trajectory_hash": "TEST_HASH_123", "wallet": "Z_TEST", "reward": 5})
    asyncio.run(n2.start())

t1 = threading.Thread(target=run_node1, daemon=True)
t2 = threading.Thread(target=run_node2, daemon=True)

t1.start()
t2.start()

time.sleep(5)
print("Test completed.")
