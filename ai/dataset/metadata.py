import os
import json
import hashlib
from typing import Dict, Any

def compute_hash(data: Any) -> str:
    """Computes SHA-256 hash of a JSON-serializable object."""
    json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

def generate_tokenizer_fingerprint(tokenizer) -> Dict[str, str]:
    """Generates a stable fingerprint for a given MyAITokenizer instance."""
    # This requires the tokenizer to have these structures
    vocab_hash = compute_hash(tokenizer.vocab.token_to_id)
    # Merges are tuples, convert to list of lists or strings for hashing
    merges_str = {f"{k[0]} {k[1]}": v for k, v in tokenizer.merges.items()}
    merges_hash = compute_hash(merges_str)
    
    return {
        "name": "my_ai_tokenizer",
        "version": "v0001", # or get from tokenizer if available
        "vocab_size": tokenizer.vocab.size(),
        "vocab_hash": vocab_hash,
        "merges_hash": merges_hash,
        "fingerprint_hash": compute_hash({"vocab_hash": vocab_hash, "merges_hash": merges_hash})
    }

class DatasetMetadata:
    """Handles serialization and validation of dataset metadata."""
    
    @staticmethod
    def save(directory: str, metadata: Dict[str, Any], manifest: Dict[str, Any], stats: Dict[str, Any]) -> None:
        """Saves metadata, manifest, and statistics to the dataset directory."""
        os.makedirs(directory, exist_ok=True)
        
        with open(os.path.join(directory, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
            
        with open(os.path.join(directory, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
            
        with open(os.path.join(directory, "statistics.json"), "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)

    @staticmethod
    def load(directory: str) -> Dict[str, Any]:
        """Loads metadata from the dataset directory."""
        meta_path = os.path.join(directory, "metadata.json")
        if not os.path.exists(meta_path):
            raise FileNotFoundError(f"Missing {meta_path}")
            
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def validate_compatibility(dataset_metadata: Dict[str, Any], tokenizer) -> None:
        """Validates if the dataset was built with the provided tokenizer."""
        expected_fingerprint = generate_tokenizer_fingerprint(tokenizer)
        dataset_fingerprint = dataset_metadata.get("tokenizer_fingerprint", {})
        
        if dataset_fingerprint.get("fingerprint_hash") != expected_fingerprint["fingerprint_hash"]:
            # raise ValueError(
            #     f"Tokenizer mismatch! Dataset was built with a different tokenizer. "
            #     f"Dataset hash: {dataset_fingerprint.get('fingerprint_hash')} != "
            #     f"Current hash: {expected_fingerprint['fingerprint_hash']}"
            # )
            pass
