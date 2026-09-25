import asyncio
import websockets
import json
import logging
import time
import os
import requests
import uuid
import socket

from p2p.protocol import MessageType, create_message, parse_message

logging.basicConfig(filename='zyra_p2p.log', level=logging.INFO, format='%(asctime)s - [P2P] %(message)s')

class P2PNode:
    def __init__(self, host='0.0.0.0', port=5001, tracker_url='http://localhost:5000', seed_peer=None):
        self.host = host
        self.port = port
        self.tracker_url = tracker_url
        self.node_id = str(uuid.uuid4())
        
        self.peers = set() # Set of websocket connections
        self.peer_addresses = set() # Set of "ws://ip:port"
        self.relay_ws = None # WebSocket connection to Bridge Relay
        
        if seed_peer:
            self.peer_addresses.add(seed_peer)
            
        # Local Mempool
        self.tasks = {} # task_id -> task_data
        self.trajectories = {} # trajectory_hash -> trajectory_data
        self.signatures = {} # trajectory_hash -> [signatures]
        
        # Keep track of seen message IDs to prevent infinite gossip loops
        self.seen_messages = set()
        
        # P2P File Transfer State
        self.hosted_files = {} # cid -> filepath
        self.downloading_files = {} # cid -> { "chunks": {}, "path": filepath }
        self.file_transfer_callbacks = {} # cid -> asyncio.Future()
        
        self.on_trajectory_received = None # Callback function
        
    async def start(self):
        self.loop = asyncio.get_running_loop()
        
        # 1. Start the local server to listen for incoming peer connections (LAN)
        try:
            server = await websockets.serve(self.handle_client, self.host, self.port)
            logging.info(f"P2P Node started on ws://{self.host}:{self.port}")
        except Exception as e:
            logging.warning(f"Could not start local P2P server: {e}")
        
        # 2. Connect to Bridge WebSocket Relay (primary P2P transport)
        asyncio.create_task(self.connect_to_relay())
        
        # 3. Register with Bootstrap Tracker to get other peers
        self.register_with_tracker()
        
        # 4. Connect to known peers (direct, for LAN)
        await self.connect_to_peers()
        
        # 5. Keep alive / Sync loop
        asyncio.create_task(self.sync_loop())
        
        await asyncio.Future()  # run forever

    async def connect_to_relay(self):
        """Connect to the Bridge WebSocket Relay for NAT-traversal P2P."""
        from urllib.parse import urlparse
        parsed = urlparse(self.tracker_url)
        relay_host = parsed.hostname or "localhost"
        relay_port = int(os.environ.get("WS_RELAY_PORT", 5050))
        relay_uri = f"ws://{relay_host}:{relay_port}"
        
        while True:
            try:
                self.relay_ws = await websockets.connect(relay_uri)
                self.peers.add(self.relay_ws)
                logging.info(f"Connected to Bridge WebSocket Relay at {relay_uri}")
                print(f"[\033[92mP2P\033[0m] Connected to Bridge Relay ({relay_uri})")
                
                # Listen to relay messages
                try:
                    async for message_str in self.relay_ws:
                        msg = parse_message(message_str)
                        if not msg:
                            continue
                        await self.handle_message(msg, self.relay_ws, message_str)
                except websockets.exceptions.ConnectionClosed:
                    logging.warning("Bridge Relay connection closed.")
                    self.peers.discard(self.relay_ws)
                    self.relay_ws = None
                    
            except Exception as e:
                logging.warning(f"Failed to connect to Bridge Relay ({relay_uri}): {e}")
                print(f"[\033[91mDEBUG P2P\033[0m] Miner failed to connect to Relay Server at {relay_uri}! Error: {e}. Check Firewall Port 5050!")
            
            # Reconnect after 10 seconds
            await asyncio.sleep(10)

    def get_public_ip(self):
        # Resolve the correct local IP interface by targeting the tracker
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            from urllib.parse import urlparse
            tracker_domain = urlparse(self.tracker_url).hostname
            if not tracker_domain or tracker_domain in ['localhost', '127.0.0.1', '0.0.0.0']:
                tracker_domain = '10.255.255.255'
                
            # The OS routing table will automatically pick the correct IP (e.g., Tailscale or WiFi)
            s.connect((tracker_domain, 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    def register_with_tracker(self):
        try:
            ip = self.get_public_ip()
            ws_url = f"ws://{ip}:{self.port}"
            res = requests.post(f"{self.tracker_url}/register_peer", json={"ws_url": ws_url}, timeout=2)
            if res.status_code == 200:
                peers = res.json().get("peers", [])
                for p in peers:
                    if p != ws_url:
                        self.peer_addresses.add(p)
                logging.info(f"Registered with Tracker. Found {len(self.peer_addresses)} peers.")
        except Exception as e:
            logging.warning(f"Failed to register with Tracker: {e}. Will run in isolated mode.")

    async def connect_to_peers(self):
        for addr in list(self.peer_addresses):
            asyncio.create_task(self.connect_to_peer(addr))

    async def connect_to_peer(self, uri):
        try:
            websocket = await websockets.connect(uri)
            self.peers.add(websocket)
            logging.info(f"Connected to peer: {uri}")
            
            # Request mempool sync
            await websocket.send(create_message(MessageType.SYNC_MEMPOOL))
            
            # Listen to this peer
            await self.listen_to_peer(websocket)
        except Exception as e:
            logging.error(f"Could not connect to {uri}: {e}")
            self.peer_addresses.discard(uri)

    async def handle_client(self, websocket, *args, **kwargs):
        # Someone connected to us
        self.peers.add(websocket)
        remote_ip = websocket.remote_address[0]
        logging.info(f"New incoming connection from {remote_ip}")
        try:
            await self.listen_to_peer(websocket)
        finally:
            self.peers.discard(websocket)

    async def listen_to_peer(self, websocket):
        try:
            async for message_str in websocket:
                msg = parse_message(message_str)
                if not msg: continue
                
                # Deduplication to avoid infinite gossip loops
                msg_hash = hash(message_str)
                if msg_hash in self.seen_messages:
                    continue
                self.seen_messages.add(msg_hash)
                
                await self.handle_message(msg, websocket, message_str)
        except websockets.exceptions.ConnectionClosed:
            logging.info("Peer connection closed.")
        finally:
            if websocket in self.peers:
                self.peers.discard(websocket)

    async def handle_message(self, msg, websocket, raw_msg_str):
        msg_hash = hash(raw_msg_str)
        if msg_hash in self.seen_messages:
            return
        self.seen_messages.add(msg_hash)
        
        msg_type = msg.get("type")
        payload = msg.get("payload")
        
        if msg_type != MessageType.FILE_CHUNK:
            print(f"[\033[93mDEBUG P2P\033[0m] Handled msg_type: {msg_type}")
            
        if msg_type == MessageType.NEW_TASK:
            task_id = payload.get("task_id")
            if task_id not in self.tasks:
                logging.info(f"Received NEW_TASK: {task_id}")
                self.tasks[task_id] = payload
                await self.broadcast(raw_msg_str, exclude=websocket)
                
        elif msg_type == MessageType.NEW_TRAJECTORY:
            traj_hash = payload.get("trajectory_hash")
            if traj_hash not in self.trajectories:
                logging.info(f"Received NEW_TRAJECTORY: {traj_hash}")
                self.trajectories[traj_hash] = payload
                if self.on_trajectory_received:
                    # Fire callback in a separate task or directly
                    self.on_trajectory_received(payload)
                await self.broadcast(raw_msg_str, exclude=websocket)
                
        elif msg_type == MessageType.VALIDATION_SIGNATURE:
            traj_hash = payload.get("trajectory_hash")
            sig = payload.get("signature")
            if traj_hash not in self.signatures:
                self.signatures[traj_hash] = []
            if sig not in self.signatures[traj_hash]:
                logging.info(f"Received VALIDATION_SIGNATURE for {traj_hash}")
                self.signatures[traj_hash].append(sig)
                await self.broadcast(raw_msg_str, exclude=websocket)
                
        elif msg_type == MessageType.SYNC_MEMPOOL:
            # Send our current state
            sync_data = {
                "tasks": self.tasks,
                "trajectories": self.trajectories,
                "signatures": self.signatures
            }
            await websocket.send(create_message(MessageType.MEMPOOL_DATA, sync_data))
            
        elif msg_type == MessageType.MEMPOOL_DATA:
            logging.info("Received MEMPOOL_DATA sync")
            self.tasks.update(payload.get("tasks", {}))
            self.trajectories.update(payload.get("trajectories", {}))
            # Merge signatures
            for t_hash, sigs in payload.get("signatures", {}).items():
                if t_hash not in self.signatures:
                    self.signatures[t_hash] = []
                for s in sigs:
                    if s not in self.signatures[t_hash]:
                        self.signatures[t_hash].append(s)
                        
        elif msg_type == MessageType.FILE_OFFER:
            cid = payload.get("cid")
            # Just forward the offer to others
            await self.broadcast(raw_msg_str, exclude=websocket)
            
        elif msg_type == MessageType.FILE_REQUEST:
            cid = payload.get("cid")
            print(f"[\033[93mDEBUG P2P\033[0m] FILE_REQUEST received for {cid}. My hosted files: {list(self.hosted_files.keys())}")
            if cid in self.hosted_files:
                print(f"[\033[96mP2P Node\033[0m] Found requested file {cid}. Starting upload...")
                asyncio.create_task(self.send_file_chunks(cid, websocket))
            else:
                await self.broadcast(raw_msg_str, exclude=websocket)
                
        elif msg_type == MessageType.FILE_CHUNK:
            cid = payload.get("cid")
            chunk_index = payload.get("chunk_index")
            data = payload.get("data")
            
            if cid in self.downloading_files:
                dl = self.downloading_files[cid]
                if chunk_index == -1:
                    # EOF - Reconstruct file
                    print(f"[\033[92mP2P Node\033[0m] Received EOF for {cid}. Assembling file...")
                    import base64
                    try:
                        with open(dl["path"], 'wb') as f:
                            for i in sorted(dl["chunks"].keys()):
                                f.write(base64.b64decode(dl["chunks"][i]))
                        print(f"[\033[92mSUCCESS\033[0m] File {cid} assembled successfully.")
                        if cid in self.file_transfer_callbacks:
                            if not self.file_transfer_callbacks[cid].done():
                                self.file_transfer_callbacks[cid].set_result(True)
                    except Exception as e:
                        print(f"[\033[91mERROR\033[0m] Failed to assemble file {cid}: {e}")
                else:
                    dl["chunks"][chunk_index] = data
            else:
                # Act as Relay and forward the chunk
                await self.broadcast(raw_msg_str, exclude=websocket)

    async def broadcast(self, raw_msg_str, exclude=None):
        """Gossip Protocol: Send message to all connected peers"""
        print(f"[\033[93mDEBUG P2P\033[0m] Executing broadcast! Peers count: {len(self.peers)}")
        if not self.peers:
            return
            
        # Register in seen to avoid echoing back
        self.seen_messages.add(hash(raw_msg_str))
        
        disconnected = set()
        for peer in self.peers:
            if peer == exclude:
                continue
            try:
                await peer.send(raw_msg_str)
                print(f"[\033[93mDEBUG P2P\033[0m] Successfully sent message to peer.")
            except Exception as e:
                print(f"[\033[91mDEBUG P2P\033[0m] Failed to send message to peer: {e}")
                disconnected.add(peer)
                
        for peer in disconnected:
            self.peers.remove(peer)

    def seed_file(self, cid, filepath):
        """Register a file to be seeded by this node."""
        self.hosted_files[cid] = filepath
        logging.info(f"Seeding file {cid} from {filepath}")
        
        # Broadcast FILE_OFFER
        import os
        total_chunks = (os.path.getsize(filepath) // 65536) + 1
        msg = create_message(MessageType.FILE_OFFER, {"cid": cid, "total_chunks": total_chunks})
        self._run_coroutine(self.broadcast(msg))

    async def request_file(self, cid, dest_path):
        """Request a file from the P2P network and wait for completion."""
        print(f"[\033[93mDEBUG P2P\033[0m] request_file called for {cid}")
        self.downloading_files[cid] = {"chunks": {}, "path": dest_path}
        future = self.loop.create_future()
        self.file_transfer_callbacks[cid] = future
        
        logging.info(f"Broadcasting FILE_REQUEST for {cid}")
        msg = create_message(MessageType.FILE_REQUEST, {"cid": cid})
        print(f"[\033[93mDEBUG P2P\033[0m] Broadcasting FILE_REQUEST msg...")
        await self.broadcast(msg)
        print(f"[\033[93mDEBUG P2P\033[0m] Broadcast complete! Waiting for future...")
        
        # Wait until file is assembled
        await future
        return dest_path

    async def send_file_chunks(self, cid, websocket):
        """Read local file and send chunks directly over websocket."""
        filepath = self.hosted_files.get(cid)
        if not filepath: return
        
        print(f"[\033[96mP2P Node\033[0m] Sending file chunks for {cid} to Relay...")
        try:
            import base64
            with open(filepath, 'rb') as f:
                chunk_index = 0
                while True:
                    data = f.read(65536) # 64 KB chunks
                    if not data:
                        break
                    
                    b64_data = base64.b64encode(data).decode('utf-8')
                    msg = create_message(MessageType.FILE_CHUNK, {
                        "cid": cid,
                        "chunk_index": chunk_index,
                        "data": b64_data
                    })
                    await websocket.send(msg)
                    chunk_index += 1
                    
            # Send EOF chunk
            eof_msg = create_message(MessageType.FILE_CHUNK, {
                "cid": cid,
                "chunk_index": -1,
                "data": ""
            })
            await websocket.send(eof_msg)
            logging.info(f"Finished sending all chunks for {cid}.")
        except Exception as e:
            logging.error(f"Error sending file {cid}: {e}")

    # --- Public API for Local Node ---
    def _run_coroutine(self, coro):
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(coro)
            print("[\033[93mDEBUG P2P\033[0m] Scheduled coroutine on current loop.")
        except RuntimeError:
            # We are not in an event loop, or in a different thread
            # Use the saved loop
            if hasattr(self, 'loop') and self.loop:
                asyncio.run_coroutine_threadsafe(coro, self.loop)
                print("[\033[93mDEBUG P2P\033[0m] Scheduled coroutine via threadsafe.")
            else:
                logging.warning("Cannot broadcast message, no event loop running.")
                print("[\033[91mDEBUG P2P\033[0m] Cannot broadcast message, no event loop running.")

    def add_task(self, task_payload):
        task_id = task_payload["task_id"]
        self.tasks[task_id] = task_payload
        msg = create_message(MessageType.NEW_TASK, task_payload)
        self._run_coroutine(self.broadcast(msg))

    def add_trajectory(self, traj_payload):
        t_hash = traj_payload["trajectory_hash"]
        self.trajectories[t_hash] = traj_payload
        msg = create_message(MessageType.NEW_TRAJECTORY, traj_payload)
        self._run_coroutine(self.broadcast(msg))
        
    def add_signature(self, sig_payload):
        t_hash = sig_payload["trajectory_hash"]
        if t_hash not in self.signatures:
            self.signatures[t_hash] = []
        self.signatures[t_hash].append(sig_payload["signature"])
        msg = create_message(MessageType.VALIDATION_SIGNATURE, sig_payload)
        self._run_coroutine(self.broadcast(msg))

    async def sync_loop(self):
        # Periodically clean up old messages, check tracker for new peers, etc.
        while True:
            await asyncio.sleep(60)
            self.seen_messages.clear() # Prevent memory leak

if __name__ == "__main__":
    node = P2PNode(port=5001)
    asyncio.run(node.start())
