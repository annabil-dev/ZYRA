import argparse
import yaml
import logging
import torch
import os

from ai.tokenizer import MyAITokenizer
from ai.dataset.reader import DatasetReader
from ai.brain.baseline_mlp import FixedContextMLP
from ai.training.trainer import Trainer
from ai.training.checkpoint import CheckpointManager
from ai.training.reproducibility import set_seed
from app.core.logger import setup_logger

def main():
    parser = argparse.ArgumentParser(description="Train Baseline Neural Network")
    parser.add_argument("--dataset", type=str, required=True, help="Path to the compiled dataset directory")
    parser.add_argument("--config", type=str, default="configs/default.yaml", help="Path to config file")
    parser.add_argument("--tokenizer", type=str, required=True, help="Path to tokenizer directory")
    parser.add_argument("--dry-run", action="store_true", help="Run 1 step without real training")
    parser.add_argument("--sanity", action="store_true", help="Run quick 50 step sanity check")
    parser.add_argument("--device", type=str, help="Override device (cuda/cpu)")
    
    args = parser.parse_args()
    
    # 1. Setup Logging
    logger = setup_logger("train_baseline", console_only=True)
    logger.info("Initializing Phase 3 Training Pipeline")
    
    # 2. Load Config
    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    train_config = config.get("training", {})
    model_config = config.get("model", {})
    
    # Override device if specified
    if args.device:
        train_config["device"] = args.device
        
    # 3. Reproducibility
    seed = train_config.get("seed", 1337)
    set_seed(seed)
    
    # 4. Determine Device
    device_name = train_config.get("device", "auto")
    if device_name == "auto" or device_name == "cuda":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device("cpu")
    logger.info(f"Using device: {device}")
    
    # 5. Load Tokenizer & Validate
    logger.info("Loading Tokenizer...")
    tokenizer = MyAITokenizer.load(args.tokenizer)
    vocab_size = tokenizer.vocab.size()
    
    # 6. Load Dataset Reader
    logger.info("Loading Dataset...")
    try:
        reader = DatasetReader(args.dataset, tokenizer)
        # Verify vocab size matches dataset and tokenizer
        ds_vocab_size = reader.metadata.get("tokenizer_fingerprint", {}).get("vocab_size", -1)
        if ds_vocab_size != vocab_size:
            raise ValueError(f"Vocab size mismatch! Tokenizer: {vocab_size}, Dataset metadata: {ds_vocab_size}")
    except Exception as e:
        logger.error(f"Failed to load dataset: {e}")
        return
        
    # 7. Instantiate Model
    logger.info("Initializing Model: FixedContextMLP")
    model = FixedContextMLP(model_config, vocab_size).to(device)
    
    params = model.get_parameter_count()
    logger.info(f"Model parameters: {params['total_parameters']:,} (Trainable: {params['trainable_parameters']:,})")
    
    # 8. Instantiate Optimizer
    lr = train_config.get("learning_rate", 0.001)
    wd = train_config.get("weight_decay", 0.01)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    
    # 9. Checkpoint Manager
    checkpoint_dir = train_config.get("checkpoints_dir", "checkpoints/baseline")
    checkpoint_manager = CheckpointManager(checkpoint_dir)
    
    # 10. Trainer
    trainer = Trainer(
        model=model,
        optimizer=optimizer,
        train_config=train_config,
        dataset_reader=reader,
        checkpoint_manager=checkpoint_manager
    )
    
    # 11. Run
    try:
        trainer.train(dry_run=args.dry_run, sanity=args.sanity)
    except Exception as e:
        logger.error(f"Training failed with error: {e}")
        
    # 12. Final Report
    logger.info("=== TRAINING REPORT ===")
    logger.info(f"Model: {model.__class__.__name__}")
    logger.info(f"Parameters: {params['total_parameters']:,}")
    logger.info(f"Device: {device}")
    logger.info(f"Training steps completed: {trainer.global_step}")
    logger.info(f"Best validation loss: {trainer.best_val_loss:.4f}")
    
if __name__ == "__main__":
    main()
