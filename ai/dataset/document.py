import os
import json
import random
from typing import Iterator, Dict, Any, Tuple

class DocumentReader:
    """
    Reads raw documents from TXT and JSONL sources and handles document-level split logic.
    Yields documents one by one to avoid loading the entire dataset into memory.
    """
    def __init__(self, corpus_dir: str, config: Dict[str, Any]):
        self.corpus_dir = corpus_dir
        self.config = config
        self.random_seed = self.config.get("random_seed", 42)
        
        split_ratio = self.config.get("split_ratio", {"train": 0.8, "validation": 0.1, "test": 0.1})
        self.train_pct = split_ratio.get("train", 0.8)
        self.val_pct = split_ratio.get("validation", 0.1)
        self.jsonl_text_field = self.config.get("jsonl_text_field", "text")
        
        # Initialize random state
        self.rng = random.Random(self.random_seed)

    def _get_files(self) -> list:
        files = []
        for ext in (".txt", ".jsonl"):
            for root, _, filenames in os.walk(self.corpus_dir):
                for name in filenames:
                    if name.endswith(ext):
                        files.append(os.path.join(root, name))
        return sorted(files)  # deterministic order

    def _determine_split(self) -> str:
        """Deterministically decides which split a document belongs to."""
        val = self.rng.random()
        if val < self.train_pct:
            return "train"
        elif val < self.train_pct + self.val_pct:
            return "validation"
        else:
            return "test"

    def read_documents(self) -> Iterator[Tuple[str, str, str]]:
        """
        Yields (split_name, text_content, source_reference)
        """
        files = self._get_files()
        
        for file_path in files:
            source_ref = os.path.basename(file_path)
            
            if file_path.endswith(".txt"):
                # Treat the entire text file as a single document 
                # (or could be split by double newline, but instruction implies document level = file level for txt unless specified)
                # Let's treat entire txt file as one document to keep it simple, 
                # or read chunks. Instruction: "Pertahankan document boundary"
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()
                    if text.strip():
                        split = self._determine_split()
                        yield split, text, source_ref
            
            elif file_path.endswith(".jsonl"):
                # Treat each line as a document
                line_no = 0
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line_no += 1
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            text = data.get(self.jsonl_text_field, "")
                            if text:
                                split = self._determine_split()
                                yield split, text, f"{source_ref}:{line_no}"
                        except json.JSONDecodeError:
                            # Skip corrupted lines but don't fail entire stream
                            pass
