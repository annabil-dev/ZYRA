import torch
import torch.nn as nn

class RMSNorm(nn.Module):
    """
    Root Mean Square Layer Normalization.
    x_norm = x / sqrt(mean(x**2) + eps) * weight
    """
    def __init__(self, dim: int, eps: float = 1e-5):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Calculate variance (mean of squared values) along the last dimension
        variance = x.pow(2).mean(dim=-1, keepdim=True)
        
        # Normalize
        x_norm = x * torch.rsqrt(variance + self.eps)
        
        # Scale
        return self.weight * x_norm
