import os
import logging
import argparse

from ai.tokenizer.tokenizer import MyAITokenizer
from ai.dataset.builder import DatasetBuilder
from ai.training.reproducibility import set_seed

def main():
    parser = argparse.ArgumentParser(description="Build ZYRA Dataset v0.1.0")
    parser.add_argument("--corpus-dir", type=str, required=True, help="Directory containing the corpus files")
    parser.add_argument("--tokenizer-dir", type=str, required=True, help="Path to the frozen tokenizer")
    parser.add_argument("--output-dir", type=str, default="data/datasets/zyra_dataset_v0.1.0", help="Output directory for binary files")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for splitting")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    logger = logging.getLogger("dataset_builder")
    
    set_seed(args.seed)
    
    logger.info("Initializing ZYRA Dataset Builder")
    logger.info(f"Corpus: {args.corpus_dir}")
    logger.info(f"Tokenizer: {args.tokenizer_dir}")
    logger.info(f"Output: {args.output_dir}")
    
    # Load frozen tokenizer
    logger.info("Loading tokenizer...")
    tokenizer = MyAITokenizer.load(args.tokenizer_dir)
    
    # Config for DocumentReader
    config = {
        "random_seed": args.seed,
        "split_ratio": {"train": 0.9, "validation": 0.05, "test": 0.05},
        "jsonl_text_field": "text"
    }
    
    builder = DatasetBuilder(tokenizer, config, logger)
    
    # Run build
    logger.info("Starting build process. This may take a while depending on corpus size...")
    builder.build(args.corpus_dir, args.output_dir)
    
    logger.info("Dataset build completed successfully!")

if __name__ == "__main__":
    main()
