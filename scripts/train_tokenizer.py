import os
import json
import logging
import argparse
import random
from typing import Iterator

from ai.tokenizer import MyAITokenizer
from ai.training.reproducibility import set_seed

def document_iterator(jsonl_path: str, max_docs: int = -1) -> Iterator[str]:
    """Iterates over documents in a JSONL file, yielding only the text content."""
    count = 0
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if max_docs > 0 and count >= max_docs:
                break
            try:
                doc = json.loads(line)
                yield doc["text"]
                count += 1
            except Exception as e:
                pass

def main():
    parser = argparse.ArgumentParser(description="Train ZYRA Tokenizer v1.0.0")
    parser.add_argument("--corpus", type=str, required=True, help="Path to corpus JSONL file")
    parser.add_argument("--output", type=str, default="models/ZYRA/Tokenizer/v1.0.0", help="Output directory")
    parser.add_argument("--vocab-size", type=int, default=16384, help="Target vocabulary size")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for sampling")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    logger = logging.getLogger("tokenizer_trainer")
    
    set_seed(args.seed)
    
    logger.info(f"Initializing ZYRA Tokenizer Training")
    logger.info(f"Target Vocabulary Size: {args.vocab_size}")
    logger.info(f"Seed: {args.seed}")
    
    tokenizer = MyAITokenizer()
    
    logger.info(f"Training tokenizer on {args.corpus}...")
    
    texts = list(document_iterator(args.corpus))
    
    logger.info(f"Loaded {len(texts)} documents into memory for BPE training.")
    
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    try:
        # Write to a few files in temp dir
        logger.info(f"Writing {len(texts)} documents to temporary directory for training...")
        with open(os.path.join(temp_dir, "corpus_0.txt"), "w", encoding="utf-8") as f:
            for text in texts:
                f.write(text + "\n\n")
                
        tokenizer.train(temp_dir, vocab_size=args.vocab_size)
    finally:
        shutil.rmtree(temp_dir)
        
    os.makedirs(args.output, exist_ok=True)
    tokenizer.save(args.output)
    
    manifest = {
        "tokenizer_name": "ZYRA Tokenizer v1.0.0",
        "vocab_size": tokenizer.vocab.size(),
        "special_tokens": tokenizer.special_tokens,
        "training_corpus": args.corpus,
        "seed": args.seed,
        "vocab_hash": tokenizer.fingerprint().get("vocab_hash", ""),
        "merges_hash": tokenizer.fingerprint().get("merges_hash", ""),
        "fingerprint": tokenizer.fingerprint()
    }
    
    with open(os.path.join(args.output, "tokenizer_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        
    logger.info(f"Tokenizer saved to {args.output}")
    logger.info(f"Actual Vocab Size: {tokenizer.vocab.size()}")
    
if __name__ == "__main__":
    main()
