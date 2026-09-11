import argparse
import yaml
import logging
import torch
import os
import datetime

from ai.tokenizer import MyAITokenizer
from ai.dataset.reader import DatasetReader
from ai.brain.model_factory import create_model
from ai.training.trainer import Trainer
from ai.training.checkpoint import CheckpointManager
from ai.training.scheduler import get_cosine_schedule_with_warmup
from ai.training.reproducibility import set_seed
from ai.models.metadata import ModelCard, ModelIdentity, ArchitectureMeta, TrainingLineage
from ai.models.registry import ModelRegistry

def main():
    parser = argparse.ArgumentParser(description="Pretrain MY-AI ZYRA-1")
    parser.add_argument("--config", type=str, required=True, help="Path to pretraining config file")
    parser.add_argument("--dataset", type=str, required=True, help="Path to the compiled dataset directory")
    parser.add_argument("--tokenizer", type=str, required=True, help="Path to tokenizer directory")
    parser.add_argument("--resume", type=str, help="Path to checkpoint to resume from")
    parser.add_argument("--dry-run", action="store_true", help="Run 1 step without real training")
    parser.add_argument("--sanity", action="store_true", help="Run quick 50 step sanity check")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    logger = logging.getLogger("pretrain")
    logger.info("Initializing ZYRA Pretraining Pipeline")
    
    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    model_meta = config.get("model", {})
    arch_config = config.get("architecture", {})
    train_config = config.get("training", {})
    
    # Generate Run ID
    run_id = f"run_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger.info(f"Training Run ID: {run_id}")
    
    # Model Identity
    identity = ModelIdentity(**model_meta)
    logger.info(f"Target Model Identity: {identity.display_name}")
    
    set_seed(train_config.get("seed", 1337))
    
    device_name = train_config.get("device", "auto")
    device = torch.device("cuda" if (device_name in ["auto", "cuda"] and torch.cuda.is_available()) else "cpu")
    logger.info(f"Using device: {device}")
    
    logger.info("Loading Tokenizer...")
    tokenizer = MyAITokenizer.load(args.tokenizer)
    vocab_size = tokenizer.vocab.size()
    
    logger.info("Loading Dataset...")
    reader = DatasetReader(args.dataset, tokenizer)
    ds_vocab_size = reader.metadata.get("tokenizer_fingerprint", {}).get("vocab_size", -1)
    if ds_vocab_size != vocab_size:
        raise ValueError(f"Vocab size mismatch! Tokenizer: {vocab_size}, Dataset metadata: {ds_vocab_size}")
        
    logger.info("Initializing Architecture...")
    model = create_model(arch_config, vocab_size).to(device)
    
    params = model.get_parameter_count()
    logger.info(f"Model parameters: {params['total_parameters']:,}")
    
    lr = train_config.get("learning_rate", 0.0003)
    wd = train_config.get("weight_decay", 0.1)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    
    scheduler = get_cosine_schedule_with_warmup(
        optimizer, 
        num_warmup_steps=train_config.get("warmup_steps", 200),
        num_training_steps=train_config.get("max_steps", 5000),
        min_lr_ratio=(train_config.get("min_learning_rate", 0.00003) / lr)
    )
    
    checkpoint_dir = train_config.get("checkpoints_dir", "models/ZYRA/ZYRA-1/Base/v0.1.0-dev/checkpoints")
    checkpoint_manager = CheckpointManager(checkpoint_dir)
    
    # Create Model Card
    card_dir = os.path.dirname(checkpoint_dir)
    os.makedirs(card_dir, exist_ok=True)
    
    lineage = TrainingLineage(run_id=run_id, total_tokens_seen=0)
    arch_meta = ArchitectureMeta(name=arch_config.get("name"), version=arch_config.get("version"))
    card = ModelCard(model=identity, architecture=arch_meta, training=lineage, parameter_count=params['total_parameters'])
    
    if not os.path.exists(os.path.join(card_dir, "model_card.yaml")):
        card.save(os.path.join(card_dir, "model_card.yaml"))
        
    # Register Model
    registry = ModelRegistry()
    registry.register_model(card, card_dir)
    
    # Resume Logic
    resume_step = 0
    resume_tokens = 0
    if args.resume:
        logger.info(f"Resuming from checkpoint: {args.resume}")
        cp_data = checkpoint_manager.load(
            args.resume, 
            model, 
            optimizer, 
            scheduler,
            tokenizer_fingerprint=reader.metadata.get("tokenizer_fingerprint")
        )
        resume_step = cp_data.get("global_step", 0)
        resume_tokens = cp_data.get("tokens_seen", 0)
        logger.info(f"Resumed from step {resume_step}, tokens seen {resume_tokens}")
        
        # Lineage update
        if "model_identity" in cp_data:
            lineage.parent_checkpoint = args.resume
            lineage.parent_version = cp_data["model_identity"].get("version")
            lineage.parent_model = cp_data["model_identity"].get("generation")
    
    trainer = Trainer(
        model=model,
        optimizer=optimizer,
        train_config=train_config,
        dataset_reader=reader,
        checkpoint_manager=checkpoint_manager,
        scheduler=scheduler,
        run_id=run_id,
        model_identity=model_meta
    )
    
    # Reporting before run
    eff_batch = train_config.get("micro_batch_size", 4) * train_config.get("gradient_accumulation_steps", 8)
    eff_tokens = eff_batch * arch_config.get("context_length", 256)
    logger.info("=== PRETRAINING RUN REPORT ===")
    logger.info(f"Effective sequence batch size: {eff_batch}")
    logger.info(f"Effective tokens per update: {eff_tokens}")
    logger.info(f"Total parameters: {params['total_parameters']:,}")
    
    if args.dry_run:
        logger.info("DRY RUN ENABLED. Running 1 step...")
        
    try:
        trainer.train(dry_run=args.dry_run, sanity=args.sanity, resume_step=resume_step, resume_tokens=resume_tokens)
    except KeyboardInterrupt:
        logger.info("Interrupted. Model card update skipped.")
        return
    except Exception as e:
        logger.error(f"Training failed with error: {e}")
        raise
        
    logger.info("=== FINAL METRICS ===")
    logger.info(f"Completed steps: {trainer.global_step}")
    logger.info(f"Total tokens seen: {trainer.tokens_seen}")
    
    # Update model card with new tokens
    card.training.total_tokens_seen = trainer.tokens_seen
    card.save(os.path.join(card_dir, "model_card.yaml"))
    
if __name__ == "__main__":
    main()
