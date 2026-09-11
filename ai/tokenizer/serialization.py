import json
import os
import yaml
from typing import Dict, Any, Tuple

class TokenizerSerializer:
    """
    Handles saving and loading of the tokenizer state.
    """
    @staticmethod
    def save(
        save_dir: str, 
        token_to_id: Dict[str, int], 
        merges: Dict[Tuple[str, str], int], 
        config: Dict[str, Any]
    ) -> None:
        """Saves the tokenizer to the given directory."""
        if os.path.exists(save_dir):
            if not os.path.isdir(save_dir):
                raise FileExistsError(f"Target {save_dir} exists and is not a directory.")
        else:
            os.makedirs(save_dir, exist_ok=True)
            
        # Save vocabulary
        vocab_path = os.path.join(save_dir, "vocab.json")
        with open(vocab_path, "w", encoding="utf-8") as f:
            json.dump(token_to_id, f, ensure_ascii=False, indent=2)
            
        # Save merges (convert tuple keys to string "A B")
        merges_str_keys = {f"{k[0]} {k[1]}": v for k, v in merges.items()}
        merges_path = os.path.join(save_dir, "merges.json")
        with open(merges_path, "w", encoding="utf-8") as f:
            json.dump(merges_str_keys, f, ensure_ascii=False, indent=2)
            
        # Save config
        config_path = os.path.join(save_dir, "tokenizer_config.yaml")
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, sort_keys=False)

    @staticmethod
    def load(load_dir: str) -> Tuple[Dict[str, int], Dict[Tuple[str, str], int], Dict[str, Any]]:
        """Loads the tokenizer state from the given directory."""
        if not os.path.isdir(load_dir):
            raise FileNotFoundError(f"Tokenizer directory not found: {load_dir}")
            
        # Load vocabulary
        vocab_path = os.path.join(load_dir, "vocab.json")
        if not os.path.exists(vocab_path):
            raise FileNotFoundError(f"Missing {vocab_path}")
        with open(vocab_path, "r", encoding="utf-8") as f:
            token_to_id = json.load(f)
            
        # Load merges
        merges_path = os.path.join(load_dir, "merges.json")
        if not os.path.exists(merges_path):
            raise FileNotFoundError(f"Missing {merges_path}")
        with open(merges_path, "r", encoding="utf-8") as f:
            merges_str_keys = json.load(f)
            # Reconstruct tuple keys
            merges = {tuple(k.split(" ")): v for k, v in merges_str_keys.items()}
            
        # Load config
        config_path = os.path.join(load_dir, "tokenizer_config.yaml")
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Missing {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            
        return token_to_id, merges, config
