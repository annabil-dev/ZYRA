import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, Any, Optional

from ai.brain.base_model import BaseLanguageModel

class FixedContextMLP(BaseLanguageModel):
    """
    A baseline causal language model using a fixed-context MLP instead of Attention.
    Takes in a context window of N tokens and predicts the next token.
    
    Architecture:
    - Token Embedding
    - Positional Embedding
    - Flatten (B, T, C) -> (B, T * C)
    - Hidden Layer (MLP) + ReLU + Dropout
    - Output Logits (B, V)
    """
    def __init__(self, config: Dict[str, Any], vocab_size: int):
        super().__init__(config, vocab_size)
        
        self.context_length = config.get("context_length", 32)
        self.embed_dim = config.get("embedding_dim", 128)
        self.hidden_dim = config.get("hidden_dim", 512)
        self.dropout_rate = config.get("dropout", 0.1)
        
        # Embeddings
        self.token_embedding = nn.Embedding(self.vocab_size, self.embed_dim)
        self.position_embedding = nn.Embedding(self.context_length, self.embed_dim)
        
        # Flattened size
        flattened_dim = self.context_length * self.embed_dim
        
        # MLP
        self.fc1 = nn.Linear(flattened_dim, self.hidden_dim)
        self.dropout = nn.Dropout(self.dropout_rate)
        self.fc2 = nn.Linear(self.hidden_dim, self.vocab_size)
        
        self.apply(self._init_weights)

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(self, input_ids: torch.Tensor, targets: Optional[torch.Tensor] = None) -> torch.Tensor:
        """
        input_ids shape: (B, T) where T must be <= self.context_length.
        If T < context_length, we need to pad or just process it (but MLP needs fixed size).
        We assume DataLoader provides exactly (B, context_length).
        """
        B, T = input_ids.size()
        
        if T > self.context_length:
            raise ValueError(f"Input sequence length {T} exceeds context length {self.context_length}")
        
        # In case T < context_length (e.g. at the end of a document if not padded),
        # this baseline architecture requires exactly context_length to match the Linear layer.
        # So we enforce T == context_length for this baseline.
        if T != self.context_length:
            raise ValueError(f"FixedContextMLP requires exactly T={self.context_length}, got T={T}")
            
        # 1. Token Embeddings
        # (B, T, embed_dim)
        tok_emb = self.token_embedding(input_ids)
        
        # 2. Positional Embeddings
        # Generate positions [0, 1, ..., T-1] on the same device as input
        positions = torch.arange(0, T, dtype=torch.long, device=input_ids.device).unsqueeze(0)
        pos_emb = self.position_embedding(positions) # (1, T, embed_dim)
        
        # Combine
        x = tok_emb + pos_emb # (B, T, embed_dim)
        
        # 3. Flatten
        x = x.view(B, -1) # (B, T * embed_dim)
        
        # 4. MLP
        x = F.relu(self.fc1(x))
        x = self.dropout(x)
        logits = self.fc2(x) # (B, vocab_size)
        
        return logits
