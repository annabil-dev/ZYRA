import json
import random
import numpy as np
import logging
from typing import Tuple, List
from ai.tokenizer.tokenizer import MyAITokenizer

class InstructionDatasetReader:
    """
    Loads a JSONL file containing conversational turns and prepares batches with loss masking.
    Format expected per line: {"conversations": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
    """
    def __init__(self, jsonl_path: str, tokenizer: MyAITokenizer):
        self.jsonl_path = jsonl_path
        self.tokenizer = tokenizer
        self.logger = logging.getLogger("instruction_reader")
        self.data = []
        self.metadata = {}
        self._load_data()

    def _load_data(self):
        with open(self.jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    if "conversations" in obj:
                        self.data.append(obj["conversations"])
                except Exception as e:
                    self.logger.warning(f"Skipping line due to error: {e}")
        self.logger.info(f"Loaded {len(self.data)} conversations from {self.jsonl_path}")

    def _format_and_tokenize(self, conversation: List[dict]) -> Tuple[List[int], List[int]]:
        """
        Formats the conversation and computes tokens and loss mask.
        Returns:
            input_ids: List of token IDs
            targets: List of token IDs where prompt tokens are masked with -100
        """
        input_ids = []
        targets = []
        
        for turn in conversation:
            role = turn.get("role", "")
            content = turn.get("content", "")
            
            if role == "user":
                text = f"User: {content}\n"
                turn_tokens = self.tokenizer.encode(text)
                input_ids.extend(turn_tokens)
                targets.extend([-100] * len(turn_tokens)) # Mask user input
                
            elif role == "assistant":
                text = f"Assistant: {content}\n"
                turn_tokens = self.tokenizer.encode(text)
                input_ids.extend(turn_tokens)
                
                # The target for the word "Assistant: " should ideally be masked too, 
                # but to keep it simple we can mask the prefix "Assistant: " and supervise the content.
                # Actually, standard SFT supervises the whole assistant turn including the special tokens.
                # We'll just supervise all of the assistant's tokens.
                targets.extend(turn_tokens)
                
        # Append EOS
        eos_id = self.tokenizer.vocab.get_id(self.tokenizer.vocab.special_tokens_map.get("eos", "<|eos|>"))
        input_ids.append(eos_id)
        targets.append(eos_id)
        
        return input_ids, targets

    def get_batch(self, split: str, batch_size: int, context_length: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Samples a batch. (ignores split as this is a simple in-memory loader for SFT).
        """
        if not self.data:
            raise ValueError("No data loaded.")
            
        X = np.full((batch_size, context_length), self.tokenizer.vocab.get_id(self.tokenizer.vocab.special_tokens_map.get("pad", "<|pad|>")), dtype=np.int64)
        Y = np.full((batch_size, context_length), -100, dtype=np.int64)
        
        for i in range(batch_size):
            conv = random.choice(self.data)
            input_ids, targets = self._format_and_tokenize(conv)
            
            # Truncate if longer than context_length + 1
            if len(input_ids) > context_length + 1:
                input_ids = input_ids[:context_length + 1]
                targets = targets[:context_length + 1]
                
            # We need X and Y shifted by 1
            x_seq = input_ids[:-1]
            y_seq = targets[1:]
            
            seq_len = len(x_seq)
            X[i, :seq_len] = x_seq
            Y[i, :seq_len] = y_seq
            
        return X, Y
