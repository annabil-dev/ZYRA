import os
import sys
import torch
import logging
from typing import Dict, Any

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.tokenizer.tokenizer import MyAITokenizer
from ai.brain.model_factory import create_model
from ai.training.checkpoint import CheckpointManager
from ai.training.trainer import Trainer
from ai.dataset.instruction_reader import InstructionDatasetReader
from app.core.logging_service import LoggingService

def main():
    # 1. Setup Logging
    logging_service = LoggingService("logs")
    logger = logging_service.get_logger("sft_training")
    logger.info("=== Starting ZYRA SFT Pipeline ===")

    # 2. Configs
    device = torch.device("cpu") # FORCED CPU FOR THERMAL SAFETY
    logger.info(f"Using device: {device} to prevent thermal throttle.")
    sft_config = {
        "learning_rate": 2e-5,
        "micro_batch_size": 1, # Ultra lightweight
        "gradient_accumulation_steps": 1,
        "max_steps": 100, # Increased for slightly better results, still safe on CPU
        "precision": "fp32", # Safe for CPU
        "eval_interval": 1000,
        "checkpoint_interval": 10,
        "log_interval": 1,
        "optimizer": "adamw",
        "weight_decay": 0.01
    }
    
    # 3. Load Tokenizer
    tokenizer_dir = "models/ZYRA/Tokenizer/v1.0.0"
    if not os.path.exists(tokenizer_dir):
        logger.error(f"Tokenizer not found at {tokenizer_dir}")
        return
    tokenizer = MyAITokenizer.load(tokenizer_dir, logger)
    
    # 4. Load SFT Dataset
    dataset_path = "data/mock_sft_dataset.jsonl"
    if not os.path.exists(dataset_path):
        logger.error(f"Mock SFT dataset not found at {dataset_path}")
        return
    dataset_reader = InstructionDatasetReader(dataset_path, tokenizer)
    
    # 5. Load Base Checkpoint
    base_ckpt_dir = "checkpoints/pilot"
    if not os.path.exists(base_ckpt_dir):
        logger.error(f"Base checkpoint directory not found at {base_ckpt_dir}")
        return
        
    cpts = [f for f in os.listdir(base_ckpt_dir) if f.endswith(".pt")]
    if not cpts:
        logger.error(f"No checkpoints found in {base_ckpt_dir}")
        return
        
    cpts.sort()
    latest_base = os.path.join(base_ckpt_dir, cpts[-1])
    logger.info(f"Loading Base Checkpoint: {latest_base}")
    
    cp_data = torch.load(latest_base, map_location='cpu', weights_only=False)
    arch_config = cp_data.get("model_config", {})
    # Extract vocab_size dynamically from the saved weights
    vocab_size = cp_data["model_state_dict"]["token_embedding.weight"].shape[0]
    
    model = create_model(arch_config, vocab_size)
    
    cm_base = CheckpointManager(base_ckpt_dir)
    cm_base.load(latest_base, model)
    model.to(device)
    
    # 6. Setup Optimizer
    optimizer = torch.optim.AdamW(
        model.parameters(), 
        lr=sft_config["learning_rate"], 
        weight_decay=sft_config["weight_decay"]
    )
    
    # 7. Setup Checkpoint Manager for SFT (New Directory!)
    sft_ckpt_dir = "checkpoints/chat"
    cm_sft = CheckpointManager(sft_ckpt_dir, retention_limit=3, prefix="brain_chat_v001")
    
    # 8. Setup Trainer
    trainer = Trainer(
        model=model,
        optimizer=optimizer,
        train_config=sft_config,
        dataset_reader=dataset_reader,
        checkpoint_manager=cm_sft,
        run_id="sft_pilot_01"
    )
    
    # 9. Start Training
    logger.info("Starting SFT Sanity Check Training Loop...")
    try:
        trainer.train(sanity=False) # Run until max_steps
        logger.info("SFT Training Completed Successfully.")
    except Exception as e:
        logger.error(f"SFT Training Failed: {e}")
        
    # Force save at the end just in case
    trainer._save_checkpoint()

if __name__ == "__main__":
    main()
