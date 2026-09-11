import os
import time
import logging
import math
import json
import torch
import datetime
import torch.nn as nn
from typing import Dict, Any, Optional, Tuple

from ai.training.checkpoint import CheckpointManager
from ai.training.metrics import TrainingMetrics
from ai.dataset.reader import DatasetReader
from ai.brain.baseline_mlp import FixedContextMLP

class Trainer:
    """
    Reusable training engine for MY-AI models.
    Supports gradient accumulation, mixed precision, and robust checkpointing.
    """
    def __init__(
        self,
        model: nn.Module,
        optimizer: torch.optim.Optimizer,
        train_config: Dict[str, Any],
        dataset_reader: Optional[DatasetReader] = None,
        checkpoint_manager: Optional[CheckpointManager] = None,
        scheduler: Optional[Any] = None,
        run_id: Optional[str] = None,
        model_identity: Optional[Dict[str, Any]] = None
    ):
        self.model = model
        self.optimizer = optimizer
        self.scheduler = scheduler
        self.config = train_config
        self.dataset_reader = dataset_reader
        self.checkpoint_manager = checkpoint_manager
        
        self.run_id = run_id
        self.model_identity = model_identity
        
        self.logger = logging.getLogger("training")
        
        # Hyperparameters
        self.micro_batch_size = self.config.get("micro_batch_size", 4)
        self.gradient_accumulation_steps = self.config.get("gradient_accumulation_steps", 8)
        self.max_steps = self.config.get("max_steps", 1000)
        self.max_tokens = self.config.get("max_tokens", float('inf'))
        self.eval_interval = self.config.get("eval_interval", 100)
        self.checkpoint_interval = self.config.get("checkpoint_interval", 250)
        self.log_interval = self.config.get("log_interval", 10)
        self.grad_clip = self.config.get("gradient_clip_norm", 1.0)
        
        self.device = next(model.parameters()).device
        self.use_amp = self.config.get("precision", "auto") == "amp" and self.device.type == "cuda"
        self.scaler = torch.amp.GradScaler(enabled=self.use_amp)
        
        # State
        self.global_step = 0
        self.tokens_seen = 0
        self.best_val_loss = float('inf')
        self.metrics = TrainingMetrics()
        
        # Metrics Logging
        self.metrics_file = None
        if self.run_id:
            os.makedirs(f"training_runs/{self.run_id}", exist_ok=True)
            self.metrics_file = f"training_runs/{self.run_id}/metrics.jsonl"
            
        # Loss function
        self.criterion = nn.CrossEntropyLoss()

    def _log_metric(self, record: Dict[str, Any]):
        if self.metrics_file:
            with open(self.metrics_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")

    def train(self, dry_run: bool = False, sanity: bool = False, resume_step: int = 0, resume_tokens: int = 0):
        """Starts or resumes the training loop."""
        self.model.train()
        self.logger.info(f"Starting training on device: {self.device}")
        
        if self.dataset_reader is None:
            raise ValueError("DatasetReader is required for full training.")
            
        self.global_step = resume_step
        self.tokens_seen = resume_tokens
            
        context_length = getattr(self.model, "context_length", getattr(self.model, "config", {}).get("context_length", 32))
        start_time = time.time()
        
        try:
            while self.global_step < self.max_steps and self.tokens_seen < self.max_tokens:
                t0 = time.time()
                self.optimizer.zero_grad(set_to_none=True)
                accumulated_loss = 0.0
                
                # Gradient Accumulation Loop
                for micro_step in range(self.gradient_accumulation_steps):
                    try:
                        X_np, Y_np = self.dataset_reader.get_batch("train", self.micro_batch_size, context_length)
                        X = torch.from_numpy(X_np).long().to(self.device)
                        Y = torch.from_numpy(Y_np).long().to(self.device)
                    except ValueError as e:
                        self.logger.error(f"Dataset error: {e}")
                        break
                        
                    if isinstance(self.model, FixedContextMLP):
                        targets = Y[:, -1]
                    else:
                        targets = Y
                        
                    # Forward pass with AMP
                    with torch.amp.autocast(device_type=self.device.type, enabled=self.use_amp):
                        logits = self.model(X)
                        
                        if logits.dim() == 2:
                            loss = self.criterion(logits, targets)
                        else:
                            loss = self.criterion(logits.view(-1, logits.size(-1)), targets.view(-1))
                            
                        loss = loss / self.gradient_accumulation_steps
                        
                    if torch.isnan(loss) or torch.isinf(loss):
                        self.logger.error(f"NaN or Inf loss detected at global_step {self.global_step}. Stopping training.")
                        raise ValueError("Loss is NaN or Inf")
                        
                    # Backward pass
                    self.scaler.scale(loss).backward()
                    accumulated_loss += loss.item() * self.gradient_accumulation_steps
                    
                    self.tokens_seen += (self.micro_batch_size * context_length)
                    
                # Gradient Clipping & Optimizer Step
                if self.grad_clip:
                    self.scaler.unscale_(self.optimizer)
                    torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.grad_clip)
                    
                self.scaler.step(self.optimizer)
                self.scaler.update()
                
                if self.scheduler:
                    self.scheduler.step()
                
                self.global_step += 1
                dt = time.time() - t0
                
                # Logging
                if self.global_step % self.log_interval == 0 or self.global_step == 1:
                    tokens_processed = self.micro_batch_size * self.gradient_accumulation_steps * context_length
                    tok_per_sec = tokens_processed / max(dt, 0.001)
                    
                    vram_alloc_mb = 0
                    vram_res_mb = 0
                    if self.device.type == "cuda":
                        vram_alloc_mb = torch.cuda.memory_allocated() / (1024**2)
                        vram_res_mb = torch.cuda.memory_reserved() / (1024**2)
                        
                    current_lr = self.scheduler.get_last_lr()[0] if self.scheduler else self.optimizer.param_groups[0]['lr']
                    
                    log_msg = (
                        f"Step {self.global_step:05d} | Loss: {accumulated_loss:.4f} | "
                        f"LR: {current_lr:.2e} | Tok/s: {tok_per_sec:.0f}"
                    )
                    if self.device.type == "cuda":
                        log_msg += f" | VRAM: {vram_alloc_mb:.0f}/{vram_res_mb:.0f}MB"
                        
                    self.logger.info(log_msg)
                    
                    self._log_metric({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "run_id": self.run_id,
                        "step": self.global_step,
                        "tokens_seen": self.tokens_seen,
                        "train_loss": accumulated_loss,
                        "learning_rate": current_lr,
                        "step_time": dt,
                        "tokens_per_second": tok_per_sec,
                        "GPU_memory_allocated": vram_alloc_mb,
                        "GPU_memory_reserved": vram_res_mb
                    })
                    
                # Evaluation & Checkpointing
                if self.global_step % self.eval_interval == 0 and not sanity:
                    val_loss = self.evaluate()
                    is_best = val_loss < self.best_val_loss
                    if is_best:
                        self.best_val_loss = val_loss
                        
                    self._log_metric({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "run_id": self.run_id,
                        "step": self.global_step,
                        "validation_loss": val_loss
                    })
                        
                if self.global_step % self.checkpoint_interval == 0 and not sanity:
                    self._save_checkpoint(is_interrupted=False)
                
                if dry_run or (sanity and self.global_step >= 50):
                    break
                    
        except KeyboardInterrupt:
            self.logger.warning("Training interrupted by user. Saving emergency checkpoint...")
            self._save_checkpoint(is_interrupted=True)
            raise
            
        except Exception as e:
            self.logger.error(f"Training failed: {e}")
            raise
            
        total_time = time.time() - start_time
        self.logger.info(f"Training completed. Total time: {total_time:.2f}s")

    def _save_checkpoint(self, is_interrupted: bool = False):
        if self.checkpoint_manager:
            fp = self.dataset_reader.metadata.get("tokenizer_fingerprint", {}) if self.dataset_reader else {}
            ds_fp = {"dataset_hash": self.dataset_reader.metadata.get("fingerprint")} if self.dataset_reader else {}
            
            is_best = False
            if hasattr(self, 'best_val_loss'):
                # We can't easily know if the current is best without evaluating right now,
                # but if we just evaluated, best_val_loss is updated. We'll pass False here
                # because we already save best.pt in evaluation step ideally.
                pass
                
            self.checkpoint_manager.save(
                model=self.model,
                optimizer=self.optimizer,
                global_step=self.global_step,
                tokens_seen=self.tokens_seen,
                train_config=self.config,
                best_val_loss=self.best_val_loss,
                tokenizer_fingerprint=fp,
                scheduler=self.scheduler,
                run_id=self.run_id,
                model_identity=self.model_identity,
                dataset_fingerprint=ds_fp,
                is_best=is_best,
                is_interrupted=is_interrupted
            )

    @torch.inference_mode()
    def evaluate(self, eval_steps: int = 50) -> float:
        """Evaluates the model on the validation split."""
        self.model.eval()
        self.logger.info("Starting validation...")
        
        context_length = getattr(self.model, "context_length", getattr(self.model, "config", {}).get("context_length", 32))
        total_loss = 0.0
        
        try:
            for _ in range(eval_steps):
                X_np, Y_np = self.dataset_reader.get_batch("validation", self.micro_batch_size, context_length)
                X = torch.from_numpy(X_np).long().to(self.device)
                Y = torch.from_numpy(Y_np).long().to(self.device)
                
                if isinstance(self.model, FixedContextMLP):
                    targets = Y[:, -1]
                else:
                    targets = Y
                    
                with torch.amp.autocast(device_type=self.device.type, enabled=self.use_amp):
                    logits = self.model(X)
                    
                    if logits.dim() == 2:
                        loss = self.criterion(logits, targets)
                    else:
                        loss = self.criterion(logits.view(-1, logits.size(-1)), targets.view(-1))
                        
                total_loss += loss.item()
                
            avg_loss = total_loss / eval_steps
            perplexity = math.exp(avg_loss) if avg_loss < 100 else float('inf')
            self.logger.info(f"Validation finished | Val Loss: {avg_loss:.4f} | Perplexity: {perplexity:.4f}")
            
        except Exception as e:
            self.logger.error(f"Validation failed: {e}")
            avg_loss = float('inf')
            
        self.model.train()
        return avg_loss
