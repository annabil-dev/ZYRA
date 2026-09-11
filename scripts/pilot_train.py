import argparse
import yaml
import logging
import torch
import os
import sys
import copy

from ai.tokenizer import MyAITokenizer
from ai.dataset.reader import DatasetReader
from ai.brain.model_factory import create_model
from ai.training.trainer import Trainer
from ai.training.checkpoint import CheckpointManager

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True)
    parser.add_argument("--dataset", type=str, required=True)
    parser.add_argument("--tokenizer", type=str, required=True)
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--resume-step", type=int, default=0)
    parser.add_argument("--resume-tokens", type=int, default=0)
    parser.add_argument("--interrupt-at", type=int, default=-1)
    parser.add_argument("--verify-weights", type=str, default="")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    logger = logging.getLogger("pilot")

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    arch_config = config.get("architecture", {})
    train_config = config.get("training", {})
    
    # Overrides for pilot
    train_config["micro_batch_size"] = 8
    train_config["precision"] = "amp"
    train_config["checkpoint_interval"] = 50
    train_config["gradient_accumulation_steps"] = 1
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    tokenizer = MyAITokenizer.load(args.tokenizer)
    vocab_size = 16384 # Match dataset
    
    reader = DatasetReader(args.dataset, tokenizer)
    # Bypass verification for pilot
    
    model = create_model(arch_config, vocab_size).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.0003)
    checkpoint_manager = CheckpointManager("checkpoints/pilot", retention_limit=5)
    
    # Verification of weights
    if args.verify_weights:
        logger.info(f"Loading checkpoint for verification from {args.verify_weights}")
        old_model = create_model(arch_config, vocab_size).to(device)
        checkpoint_manager.load(args.verify_weights, old_model)
        
        # Load into current model too
        cp = checkpoint_manager.load(args.verify_weights, model, optimizer)
        args.resume_step = cp["global_step"]
        args.resume_tokens = cp["tokens_seen"]
        
        # Verify
        for p1, p2 in zip(old_model.parameters(), model.parameters()):
            if not torch.equal(p1, p2):
                raise ValueError("Weight mismatch after loading!")
        logger.info("Weights matched successfully!")
        
    elif args.resume_step > 0 or args.interrupt_at > 0: # Check if we need to load from checkpoint dir
        # find the latest checkpoint
        cpts = [f for f in os.listdir("checkpoints/pilot") if f.endswith(".pt")]
        if cpts:
            cpts.sort()
            latest = os.path.join("checkpoints/pilot", cpts[-1])
            logger.info(f"Resuming from {latest}")
            cp = checkpoint_manager.load(latest, model, optimizer)
            args.resume_step = cp["global_step"]
            args.resume_tokens = cp["tokens_seen"]

    train_config["max_steps"] = args.max_steps
    train_config["max_tokens"] = 1000000
    
    trainer = Trainer(
        model=model,
        optimizer=optimizer,
        train_config=train_config,
        dataset_reader=reader,
        checkpoint_manager=checkpoint_manager,
        run_id="pilot_01"
    )
    
    # Hack to simulate KeyboardInterrupt
    if args.interrupt_at > 0:
        original_get_batch = reader.get_batch
        def mocked_get_batch(*a, **kw):
            if trainer.global_step == args.interrupt_at:
                logger.info("SIMULATING KEYBOARD INTERRUPT")
                raise KeyboardInterrupt()
            return original_get_batch(*a, **kw)
        reader.get_batch = mocked_get_batch

    logger.info(f"Starting training to step {args.max_steps}...")
    trainer.train(dry_run=False, sanity=False, resume_step=args.resume_step, resume_tokens=args.resume_tokens)

if __name__ == "__main__":
    main()
