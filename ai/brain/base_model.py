import torch.nn as nn
from typing import Dict, Any, Optional
import torch

class BaseLanguageModel(nn.Module):
    """
    Base interface for all language models in MY-AI.
    Ensures a consistent forward signature for the Training Engine.
    """
    def __init__(self, config: Dict[str, Any], vocab_size: int):
        super().__init__()
        self.config = config
        self.vocab_size = vocab_size

    def forward(self, input_ids: torch.Tensor, targets: Optional[torch.Tensor] = None):
        """
        Args:
            input_ids: Tensor of shape (B, T) containing token IDs.
            targets: Optional tensor of shape (B, T) containing target token IDs for loss calculation.
                     Wait, standard PyTorch approach is to output logits and let the Trainer compute loss,
                     but accepting targets here is flexible. For Phase 3, Trainer will compute loss.
                     So we only guarantee `logits` return.

        Returns:
            logits: Tensor of shape (B, V) for next-token prediction, or (B, T, V) for sequence.
        """
        raise NotImplementedError("Subclasses must implement forward()")

    def get_parameter_count(self) -> Dict[str, int]:
        """Returns the total and trainable parameter counts."""
        total = sum(p.numel() for p in self.parameters())
        trainable = sum(p.numel() for p in self.parameters() if p.requires_grad)
        return {"total_parameters": total, "trainable_parameters": trainable}
