import json
import time

class MessageType:
    PING = "PING"
    PONG = "PONG"
    NEW_TASK = "NEW_TASK"
    NEW_TRAJECTORY = "NEW_TRAJECTORY"
    VALIDATION_SIGNATURE = "VALIDATION_SIGNATURE"
    SYNC_MEMPOOL = "SYNC_MEMPOOL"
    MEMPOOL_DATA = "MEMPOOL_DATA"
    FILE_OFFER = "FILE_OFFER"
    FILE_REQUEST = "FILE_REQUEST"
    FILE_CHUNK = "FILE_CHUNK"
    TASK_UPDATED = "TASK_UPDATED"

def create_message(msg_type, payload=None):
    return json.dumps({
        "type": msg_type,
        "payload": payload or {},
        "timestamp": time.time()
    })

def parse_message(data_str):
    try:
        return json.loads(data_str)
    except json.JSONDecodeError:
        return None
