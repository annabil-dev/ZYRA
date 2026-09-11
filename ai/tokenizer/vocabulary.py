from typing import Dict, List, Optional
from ai.tokenizer.byte_codec import ByteCodec

class Vocabulary:
    """
    Manages the tokenizer vocabulary mapping between strings and integer IDs.
    """
    def __init__(self, special_tokens: Optional[Dict[str, str]] = None):
        self.byte_codec = ByteCodec()
        self.token_to_id: Dict[str, int] = {}
        self.id_to_token: Dict[int, str] = {}
        self.special_tokens_map = special_tokens or {
            "pad": "<|pad|>",
            "bos": "<|bos|>",
            "eos": "<|eos|>",
            "unk": "<|unk|>"
        }
        
        self.special_tokens_set = set(self.special_tokens_map.values())
        self._initialize_base_vocab()

    def _initialize_base_vocab(self):
        """Initializes vocabulary with special tokens and all 256 base byte representations."""
        # 1. Add special tokens first
        for name, token in self.special_tokens_map.items():
            self.add_token(token)
            
        # 2. Add base byte representations (0-255)
        for i in range(256):
            base_char = self.byte_codec.byte_encoder[i]
            self.add_token(base_char)

    def add_token(self, token: str) -> int:
        """Adds a token to the vocabulary and returns its ID."""
        if token not in self.token_to_id:
            token_id = len(self.token_to_id)
            self.token_to_id[token] = token_id
            self.id_to_token[token_id] = token
        return self.token_to_id[token]

    def get_id(self, token: str) -> int:
        """Returns the ID for a given token."""
        return self.token_to_id.get(token, self.token_to_id.get(self.special_tokens_map["unk"], 0))

    def get_token(self, token_id: int) -> str:
        """Returns the token for a given ID."""
        if token_id not in self.id_to_token:
            raise ValueError(f"Token ID {token_id} not found in vocabulary.")
        return self.id_to_token[token_id]

    def size(self) -> int:
        """Returns the current size of the vocabulary."""
        return len(self.token_to_id)
