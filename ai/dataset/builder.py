import os
import json
import logging
import numpy as np
from typing import Dict, Any, List

from ai.tokenizer.tokenizer import MyAITokenizer
from ai.dataset.document import DocumentReader
from ai.dataset.metadata import DatasetMetadata, generate_tokenizer_fingerprint

class DatasetBuilder:
    """
    Builds the dataset incrementally by writing token IDs to binary files.
    """
    def __init__(self, tokenizer: MyAITokenizer, config: Dict[str, Any], logger: logging.Logger):
        self.tokenizer = tokenizer
        self.config = config
        self.logger = logger
        
        # Decide dtype based on vocab size
        self.vocab_size = self.tokenizer.vocab.size()
        self.dtype = np.uint16 if self.vocab_size <= 65535 else np.uint32
        
        self.eos_id = self.tokenizer.vocab.get_id(self.tokenizer.config.get("special_tokens", {}).get("eos", "<|eos|>"))

    def build(self, corpus_dir: str, output_dir: str) -> None:
        """
        Builds the memory-mapped binary dataset from raw corpus.
        """
        os.makedirs(output_dir, exist_ok=True)
        self.logger.info(f"Starting dataset build in {output_dir}")
        self.logger.info(f"Using dtype {self.dtype.__name__} for vocab size {self.vocab_size}")
        
        reader = DocumentReader(corpus_dir, self.config)
        
        # We will use normal file writing (append mode) for the temporary bin files 
        # because memmap resizing is inefficient. Once written, they can be read via memmap.
        
        # Setup temporary files and states
        splits = ["train", "validation", "test"]
        tmp_files = {s: os.path.join(output_dir, f"{s}.tmp.bin") for s in splits}
        file_handles = {s: open(tmp_files[s], "wb") for s in splits}
        
        indices = {s: [] for s in splits}
        token_counts = {s: 0 for s in splits}
        doc_counts = {s: 0 for s in splits}
        total_raw_bytes = 0
        min_doc_tokens = float('inf')
        max_doc_tokens = 0
        
        # Streaming Process
        for split, text, source_ref in reader.read_documents():
            total_raw_bytes += len(text.encode("utf-8"))
            
            # Encode text
            token_ids = self.tokenizer.encode(text)
            
            # Add EOS token
            token_ids.append(self.eos_id)
            doc_token_count = len(token_ids)
            
            # Update min/max
            if doc_token_count < min_doc_tokens: min_doc_tokens = doc_token_count
            if doc_token_count > max_doc_tokens: max_doc_tokens = doc_token_count
            
            # Write to binary temporary file
            arr = np.array(token_ids, dtype=self.dtype)
            file_handles[split].write(arr.tobytes())
            
            # Record Index
            # Index: [doc_id, start_token, token_count, source_ref]
            indices[split].append({
                "doc_id": doc_counts[split],
                "start_token": token_counts[split],
                "token_count": doc_token_count,
                "source_ref": source_ref
            })
            
            token_counts[split] += doc_token_count
            doc_counts[split] += 1
            
            if (sum(doc_counts.values())) % 1000 == 0:
                self.logger.info(f"Processed {sum(doc_counts.values())} documents...")

        # Close all temp files
        for f in file_handles.values():
            f.close()
            
        # Check for empty dataset
        total_docs = sum(doc_counts.values())
        if total_docs == 0:
            for tf in tmp_files.values():
                if os.path.exists(tf): os.remove(tf)
            raise ValueError("Empty dataset. No valid documents found in corpus.")
            
        # Atomic Finalize: Rename .tmp.bin to .bin and write indices
        manifest = {}
        for s in splits:
            final_bin = os.path.join(output_dir, f"{s}.bin")
            tmp_bin = tmp_files[s]
            if os.path.exists(final_bin):
                os.remove(final_bin) # overwrite
            os.rename(tmp_bin, final_bin)
            manifest[f"{s}_bin"] = f"{s}.bin"
            
            # Write Index (JSON for simplicity and readability, though pickle/binary is smaller)
            idx_path = os.path.join(output_dir, f"{s}.idx")
            with open(idx_path, "w", encoding="utf-8") as idx_f:
                json.dump(indices[s], idx_f)
            manifest[f"{s}_idx"] = f"{s}.idx"
            
        # Save Metadata and Stats
        metadata = {
            "dtype": self.dtype.__name__,
            "tokenizer_fingerprint": generate_tokenizer_fingerprint(self.tokenizer)
        }
        
        total_tokens = sum(token_counts.values())
        stats = {
            "number_of_documents": total_docs,
            "raw_bytes": total_raw_bytes,
            "total_tokens": total_tokens,
            "train_tokens": token_counts["train"],
            "validation_tokens": token_counts["validation"],
            "test_tokens": token_counts["test"],
            "average_tokens_per_document": total_tokens / total_docs if total_docs > 0 else 0,
            "minimum_document_tokens": min_doc_tokens if min_doc_tokens != float('inf') else 0,
            "maximum_document_tokens": max_doc_tokens,
            "binary_file_sizes": {s: os.path.getsize(os.path.join(output_dir, f"{s}.bin")) for s in splits}
        }
        
        DatasetMetadata.save(output_dir, metadata, manifest, stats)
        self.logger.info(f"Dataset build completed successfully in {output_dir}")
