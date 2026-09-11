import os
import json
import numpy as np
import random
import logging
from typing import Dict, Any, Tuple, List

from ai.tokenizer.tokenizer import MyAITokenizer
from ai.dataset.metadata import DatasetMetadata

class DatasetReader:
    """
    Loads and provides streaming access to the memory-mapped dataset.
    """
    def __init__(self, dataset_dir: str, tokenizer: MyAITokenizer):
        self.dataset_dir = dataset_dir
        self.tokenizer = tokenizer
        
        # Load and Validate Metadata
        self.metadata = DatasetMetadata.load(self.dataset_dir)
        DatasetMetadata.validate_compatibility(self.metadata, self.tokenizer)
        
        # Extract dtype
        dtype_str = self.metadata.get("dtype", "uint16")
        self.dtype = np.uint16 if dtype_str == "uint16" else np.uint32
        
        # Memory-mapped files and indices
        self.memmaps = {}
        self.indices = {}
        self.token_counts = {}
        
        self._load_split("train")
        self._load_split("validation")
        self._load_split("test")

    def _load_split(self, split: str) -> None:
        bin_path = os.path.join(self.dataset_dir, f"{split}.bin")
        idx_path = os.path.join(self.dataset_dir, f"{split}.idx")
        
        if not os.path.exists(bin_path) or not os.path.exists(idx_path):
            raise FileNotFoundError(f"Missing binary or index file for split: {split}")
            
        # Verify file size is a multiple of dtype size
        file_size = os.path.getsize(bin_path)
        item_size = np.dtype(self.dtype).itemsize
        if file_size % item_size != 0:
            raise ValueError(f"Truncated binary file: {bin_path} is not aligned with dtype {self.dtype}")
            
        token_count = file_size // item_size
        self.token_counts[split] = token_count
        
        # Load memmap
        if token_count == 0:
            self.memmaps[split] = np.array([], dtype=self.dtype)
        else:
            self.memmaps[split] = np.memmap(bin_path, dtype=self.dtype, mode='r', shape=(token_count,))
            
        # Load indices
        with open(idx_path, "r", encoding="utf-8") as f:
            self.indices[split] = json.load(f)

    def get_batch(self, split: str, batch_size: int, context_length: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Samples a batch of shape (batch_size, context_length) for input (X) and target (Y).
        Target is input shifted by 1.
        Random sampling is done by picking a random start index.
        """
        if split not in self.memmaps:
            raise ValueError(f"Invalid split: {split}")
            
        mmap = self.memmaps[split]
        total_tokens = self.token_counts[split]
        
        # Need N+1 tokens to form X and Y
        sample_length = context_length + 1
        
        if total_tokens < sample_length:
            raise ValueError(f"Dataset split {split} has fewer tokens ({total_tokens}) than required sample length ({sample_length})")
            
        X = np.zeros((batch_size, context_length), dtype=np.int64)
        Y = np.zeros((batch_size, context_length), dtype=np.int64)
        
        for i in range(batch_size):
            # Randomize start index (avoid physically shuffling binary)
            start_idx = random.randint(0, total_tokens - sample_length)
            
            # Read slice (lazy via memmap)
            chunk = mmap[start_idx : start_idx + sample_length]
            
            # Validate out-of-vocab tokens (as an extra safety, though training shouldn't have them)
            # If vocab size is small, we can assert. 
            # (In production, maybe skip this inner loop check for performance)
            
            X[i] = chunk[0 : context_length]
            Y[i] = chunk[1 : context_length + 1]
            
        return X, Y

    def get_document(self, split: str, doc_index: int) -> List[int]:
        """Retrieves a specific document's tokens by its index."""
        if split not in self.indices:
            raise ValueError(f"Invalid split: {split}")
            
        docs = self.indices[split]
        if doc_index < 0 or doc_index >= len(docs):
            raise IndexError(f"Document index {doc_index} out of bounds.")
            
        doc_info = docs[doc_index]
        start = doc_info["start_token"]
        count = doc_info["token_count"]
        
        mmap = self.memmaps[split]
        # Return as python list
        return mmap[start : start + count].tolist()
