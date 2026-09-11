import torch
import torch.nn as nn
from typing import Dict, Any, Optional

from .base_model import BaseLanguageModel
from .rms_norm import RMSNorm
from .rope import RotaryPositionalEmbedding
from .transformer_block import TransformerBlock

class MyAIDecoderTransformer(BaseLanguageModel):
    """
    MY-AI Brain v0.1: Decoder-Only Causal Transformer.
    """
    def __init__(self, config: Dict[str, Any], vocab_size: int):
        super().__init__(config, vocab_size)
        
        self.context_length = config.get("context_length", 256)
        self.hidden_size = config.get("hidden_size", 512)
        self.num_layers = config.get("num_layers", 8)
        self.tie_word_embeddings = config.get("tie_word_embeddings", True)
        self.eps = config.get("rms_norm_eps", 1e-5)
        self.rope_theta = config.get("rope_theta", 10000.0)
        self.dropout_rate = config.get("dropout", 0.0)
        
        # Token Embedding
        self.token_embedding = nn.Embedding(self.vocab_size, self.hidden_size)
        self.dropout = nn.Dropout(self.dropout_rate)
        
        # RoPE (Shared across blocks)
        self.rope = RotaryPositionalEmbedding(
            dim=self.hidden_size // config.get("num_attention_heads", 8),
            max_seq_len=self.context_length,
            base=self.rope_theta
        )
        
        # Transformer Blocks
        self.blocks = nn.ModuleList([TransformerBlock(config) for _ in range(self.num_layers)])
        
        # Final Norm
        self.final_norm = RMSNorm(self.hidden_size, eps=self.eps)
        
        # Language Modeling Head
        self.lm_head = nn.Linear(self.hidden_size, self.vocab_size, bias=False)
        
        # Weight Tying
        if self.tie_word_embeddings:
            self.lm_head.weight = self.token_embedding.weight
            
        self.apply(self._init_weights)
        
    def _init_weights(self, module):
        """Centralized initialization strategy."""
        if isinstance(module, nn.Linear):
            # Normal init
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
            
        # Residual projection considerations (optional scaling down for deeper networks)
        # We can scale down attention output and FFN down projection by 1/sqrt(2 * num_layers)
        if isinstance(module, nn.Linear) and hasattr(module, "MYAI_RESIDUAL_PROJ"):
            std = 0.02 / (2 * self.num_layers) ** 0.5
            torch.nn.init.normal_(module.weight, mean=0.0, std=std)
            
    def forward(self, input_ids: torch.Tensor, targets: Optional[torch.Tensor] = None) -> torch.Tensor:
        """
        Args:
            input_ids: (B, T)
            targets: Optional, but Trainer handles loss currently.
            
        Returns:
            logits: (B, T, V)
        """
        B, T = input_ids.size()
        
        if T > self.context_length:
            raise ValueError(f"Sequence length {T} exceeds model context length {self.context_length}")
            
        # 1. Embeddings
        # (B, T, D)
        x = self.token_embedding(input_ids)
        x = self.dropout(x)
        
        # 2. Transformer Blocks
        for block in self.blocks:
            x = block(x, self.rope)
            
        # 3. Final Norm
        x = self.final_norm(x)
        
        # 4. LM Head
        # logits: (B, T, V)
        logits = self.lm_head(x)
        
        return logits
