import os
import re
import datetime
from typing import List, Dict, Optional, Any
import logging

from ai.tokenizer.vocabulary import Vocabulary
from ai.tokenizer.bpe import BPE
from ai.tokenizer.trainer import TokenizerTrainer
from ai.tokenizer.serialization import TokenizerSerializer

class MyAITokenizer:
    """
    Main interface for the MY-AI Byte-Level BPE Tokenizer.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None, logger: Optional[logging.Logger] = None):
        self.config = config or {}
        self.logger = logger or logging.getLogger("tokenizer")
        
        special_tokens = self.config.get("special_tokens", {
            "pad": "<|pad|>",
            "bos": "<|bos|>",
            "eos": "<|eos|>",
            "unk": "<|unk|>"
        })
        
        self.vocab = Vocabulary(special_tokens=special_tokens)
        self.merges = {}
        
        # Pre-tokenizer regex
        self.pat = re.compile(r"""'s|'t|'re|'ve|'m|'ll|'d| ?[a-zA-Z]+| ?[0-9]+| ?[^\s0-9a-zA-Z]+|\s+(?!\S)|\s+""")

    def train(self, corpus_dir: str, vocab_size: int, min_frequency: int = 2) -> None:
        """Trains the tokenizer on the given corpus."""
        trainer = TokenizerTrainer(self.vocab, self.logger)
        self.merges = trainer.train(corpus_dir, vocab_size, min_frequency)

    def encode(self, text: str) -> List[int]:
        """Encodes text into a list of token IDs."""
        if not text:
            return []
            
        bpe_tokens = []
        words = self.pat.findall(text)
        
        for w in words:
            # 1. UTF-8 bytes
            w_bytes = w.encode("utf-8")
            # 2. Byte Codec encoding
            w_encoded = self.vocab.byte_codec.encode_bytes(w_bytes)
            # 3. BPE Merge
            bpe_words = BPE.encode_word(w_encoded, self.merges)
            bpe_tokens.extend(bpe_words)
            
        # Map to IDs
        token_ids = [self.vocab.get_id(token) for token in bpe_tokens]
        return token_ids

    def decode(self, token_ids: List[int]) -> str:
        """Decodes a list of token IDs back into text."""
        if not token_ids:
            return ""
            
        # 1. Map IDs to tokens
        text_tokens = [self.vocab.get_token(tid) for tid in token_ids]
        text_joined = "".join(text_tokens)
        # 2. Decode Byte Codec string to raw bytes
        raw_bytes = self.vocab.byte_codec.decode_string(text_joined)
        # 3. Decode raw bytes to UTF-8 text (ignore errors on partial bytes if any)
        text = raw_bytes.decode("utf-8", errors="replace")
        return text

    def save(self, save_dir: str) -> None:
        """Saves the tokenizer to disk."""
        self.logger.info(f"Saving tokenizer to {save_dir}")
        
        meta_config = {
            "name": "my_ai_tokenizer",
            "version": "v0001",
            "type": "byte_level_bpe",
            "vocab_size": self.vocab.size(),
            "special_tokens": self.vocab.special_tokens_map,
            "training_date": datetime.datetime.now().isoformat(),
            "algorithm_version": "1.0"
        }
        
        TokenizerSerializer.save(save_dir, self.vocab.token_to_id, self.merges, meta_config)
        self.logger.info("Tokenizer saved")

    @classmethod
    def load(cls, load_dir: str, logger: Optional[logging.Logger] = None) -> "MyAITokenizer":
        """Loads a tokenizer from disk."""
        token_to_id, merges, config = TokenizerSerializer.load(load_dir)
        
        tokenizer = cls(config=config, logger=logger)
        
        # Restore vocab
        tokenizer.vocab.token_to_id = token_to_id
        tokenizer.vocab.id_to_token = {v: k for k, v in token_to_id.items()}
        
        # Restore merges
        tokenizer.merges = merges
        
        if logger:
            logger.info(f"Loaded tokenizer from {load_dir}. Vocab size: {tokenizer.vocab.size()}")
            
        return tokenizer
