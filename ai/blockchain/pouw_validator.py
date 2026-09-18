import hashlib
import json
import time
import math

class PoUWValidator:
    """
    Proof of Useful Work (PoUW) Validator.
    Instead of hashing empty blocks, we validate the computational work done during AI inference/agent tasks.
    """
    
    BASE_REWARD_PER_TOKEN = 0.0001
    DIFFICULTY_MULTIPLIER = 1.0

    @classmethod
    def calculate_reward(cls, tokens_generated: int, latency_ms: float, vram_mb: float, is_tool_call: bool) -> float:
        """
        Calculates the amount of ZYRA to reward based on the useful work performed.
        Heavier tasks (more tokens, using tools, utilizing more VRAM) yield higher rewards.
        """
        if tokens_generated <= 0:
            return 0.0
            
        # Base reward scales linearly with tokens generated
        base = tokens_generated * cls.BASE_REWARD_PER_TOKEN
        
        # Multiplier for tool usage (Agentic work is more valuable than passive chat)
        tool_multiplier = 1.5 if is_tool_call else 1.0
        
        # Hardware multiplier (Simulates higher rewards for offering more compute power)
        # Using log10 so it doesn't scale infinitely
        hw_multiplier = math.log10(max(10, vram_mb)) / math.log10(8192) if vram_mb > 0 else 1.0
        
        # Calculate final reward
        reward = base * tool_multiplier * hw_multiplier * cls.DIFFICULTY_MULTIPLIER
        
        # Cap reward per single inference task to prevent abuse
        return round(min(reward, 50.0), 6)

    @classmethod
    def generate_proof(cls, task_type: str, prompt: str, tokens: int, metrics: dict, wallet_address: str) -> dict:
        """
        Generates a cryptographic proof of the work done.
        In a real P2P network, nodes would verify this proof against a model checkpoint.
        For local simulation, we sign the metrics with the system timestamp.
        """
        timestamp = time.time()
        
        # Check if tools were used (indicated by task_type or metrics)
        is_tool = task_type == 'AGENT_EXECUTION'
        
        vram_mb = metrics.get('vram_mb', 0.0)
        latency_ms = metrics.get('latency_ms', 0.0)
        
        reward = cls.calculate_reward(tokens, latency_ms, vram_mb, is_tool)
        
        proof_payload = {
            "task_type": task_type,
            "wallet": wallet_address,
            "tokens": tokens,
            "metrics": metrics,
            "timestamp": timestamp,
            "reward": reward
        }
        
        # Create a verifiable hash of the payload
        payload_str = json.dumps(proof_payload, sort_keys=True)
        proof_hash = hashlib.sha256(payload_str.encode()).hexdigest()
        
        proof_payload["proof_hash"] = proof_hash
        
        return proof_payload
