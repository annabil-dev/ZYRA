import os
import torch
import logging
import random
import numpy as np
from typing import Dict, Any, Optional
import datetime

class CheckpointManager:
    """
    Handles robust saving and loading of model checkpoints for ZYRA models.
    Uses atomic writes to prevent corruption.
    """
    def __init__(self, checkpoint_dir: str, retention_limit: int = 3, prefix: str = "step"):
        self.checkpoint_dir = checkpoint_dir
        self.retention_limit = retention_limit
        self.prefix = prefix
        self.logger = logging.getLogger("checkpoint")
        
        os.makedirs(self.checkpoint_dir, exist_ok=True)

    def _get_rng_state(self) -> Dict[str, Any]:
        """Captures all RNG states."""
        state = {
            "python": random.getstate(),
            "numpy": np.random.get_state(),
            "torch_cpu": torch.get_rng_state(),
        }
        if torch.cuda.is_available():
            state["torch_cuda"] = torch.cuda.get_rng_state_all()
        return state
        
    def _set_rng_state(self, state: Dict[str, Any]):
        """Restores all RNG states."""
        try:
            if "python" in state:
                random.setstate(state["python"])
            if "numpy" in state:
                np.random.set_state(state["numpy"])
            if "torch_cpu" in state:
                torch.set_rng_state(state["torch_cpu"])
            if "torch_cuda" in state and torch.cuda.is_available():
                torch.cuda.set_rng_state_all(state["torch_cuda"])
            self.logger.info("RNG state restored successfully.")
        except Exception as e:
            self.logger.warning(f"Failed to restore full RNG state: {e}")

    def save(
        self, 
        model: torch.nn.Module, 
        optimizer: torch.optim.Optimizer, 
        global_step: int,
        tokens_seen: int,
        train_config: Dict[str, Any],
        best_val_loss: float,
        tokenizer_fingerprint: Dict[str, Any],
        scheduler: Optional[Any] = None,
        run_id: Optional[str] = None,
        model_identity: Optional[Dict[str, Any]] = None,
        dataset_fingerprint: Optional[Dict[str, Any]] = None,
        is_best: bool = False,
        is_interrupted: bool = False
    ) -> None:
        """Saves a checkpoint atomically."""
        if is_interrupted:
            filename = f"{self.prefix}_{global_step:08d}_INTERRUPTED.pt"
        else:
            filename = f"{self.prefix}_{global_step:08d}.pt"
            
        final_path = os.path.join(self.checkpoint_dir, filename)
        tmp_path = final_path + ".tmp"
        
        checkpoint_data = {
            "format_version": "2.0",
            "model_identity": model_identity or {},
            "architecture": model.__class__.__name__,
            "model_config": getattr(model, "config", {}),
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict() if scheduler else None,
            "global_step": global_step,
            "tokens_seen": tokens_seen,
            "training_config": train_config,
            "run_id": run_id,
            "best_validation_loss": best_val_loss,
            "tokenizer_fingerprint": tokenizer_fingerprint,
            "dataset_fingerprint": dataset_fingerprint or {},
            "rng_state": self._get_rng_state(),
            "pytorch_version": torch.__version__,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        try:
            # 1. Save to temporary file
            torch.save(checkpoint_data, tmp_path)
            
            # 2. Atomic rename
            if os.path.exists(final_path):
                os.remove(final_path)
            os.rename(tmp_path, final_path)
            
            self.logger.info(f"Saved checkpoint: {final_path}")
            
            if is_best and not is_interrupted:
                best_path = os.path.join(self.checkpoint_dir, "best.pt")
                best_tmp = best_path + ".tmp"
                torch.save(checkpoint_data, best_tmp)
                if os.path.exists(best_path):
                    os.remove(best_path)
                os.rename(best_tmp, best_path)
                
            if not is_interrupted:
                self._apply_retention_policy()
            
        except Exception as e:
            self.logger.error(f"Failed to save checkpoint: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def load(
        self, 
        checkpoint_path: str, 
        model: torch.nn.Module, 
        optimizer: Optional[torch.optim.Optimizer] = None, 
        scheduler: Optional[Any] = None,
        tokenizer_fingerprint: Optional[Dict[str, Any]] = None,
        dataset_fingerprint: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Loads a checkpoint and validates compatibility."""
        if not os.path.exists(checkpoint_path):
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
            
        self.logger.info(f"Loading checkpoint from {checkpoint_path}")
        checkpoint_data = torch.load(checkpoint_path, map_location=torch.device('cpu'), weights_only=False)
        
        # 1. Validation
        if checkpoint_data["architecture"] != model.__class__.__name__:
            raise ValueError(f"Architecture mismatch: Checkpoint is {checkpoint_data['architecture']}, model is {model.__class__.__name__}")
            
        if tokenizer_fingerprint:
            cp_fp = checkpoint_data.get("tokenizer_fingerprint", {})
            if cp_fp.get("fingerprint_hash") != tokenizer_fingerprint.get("fingerprint_hash"):
                raise ValueError("Tokenizer fingerprint mismatch! Checkpoint was trained with a different tokenizer.")
                
        if dataset_fingerprint:
            cp_ds_fp = checkpoint_data.get("dataset_fingerprint", {})
            # Depending on strictness, we might warn or fail here.
            if cp_ds_fp.get("dataset_hash") and dataset_fingerprint.get("dataset_hash") != cp_ds_fp.get("dataset_hash"):
                self.logger.warning("Dataset fingerprint mismatch. Resuming on a different dataset split?")
                
        # 2. Restore State
        model.load_state_dict(checkpoint_data["model_state_dict"])
        if optimizer and "optimizer_state_dict" in checkpoint_data and checkpoint_data["optimizer_state_dict"]:
            optimizer.load_state_dict(checkpoint_data["optimizer_state_dict"])
            
        if scheduler and "scheduler_state_dict" in checkpoint_data and checkpoint_data["scheduler_state_dict"]:
            scheduler.load_state_dict(checkpoint_data["scheduler_state_dict"])
            
        if "rng_state" in checkpoint_data:
            self._set_rng_state(checkpoint_data["rng_state"])
            
        self.logger.info(f"Successfully loaded checkpoint at step {checkpoint_data.get('global_step', 0)}")
        return checkpoint_data

    def _apply_retention_policy(self):
        """Keeps only the last N checkpoints (ignores best.pt and INTERRUPTED)."""
        checkpoints = []
        for file in os.listdir(self.checkpoint_dir):
            if file.startswith(self.prefix + "_") and file.endswith(".pt") and "INTERRUPTED" not in file:
                path = os.path.join(self.checkpoint_dir, file)
                checkpoints.append(path)
                
        checkpoints.sort(key=os.path.getmtime)
        
        while len(checkpoints) > self.retention_limit:
            oldest = checkpoints.pop(0)
            os.remove(oldest)
            self.logger.debug(f"Removed old checkpoint: {oldest}")
