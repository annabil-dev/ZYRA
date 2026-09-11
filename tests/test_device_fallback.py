import pytest
import torch
from ai.brain.baseline_mlp import FixedContextMLP

def test_device_alignment():
    # If CUDA is available, test placing model on CUDA
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")
        
    device = torch.device("cuda")
    config = {"context_length": 4, "embedding_dim": 16, "hidden_dim": 32, "dropout": 0.0}
    
    model = FixedContextMLP(config, 50).to(device)
    
    # Input on CPU
    X_cpu = torch.randint(0, 50, (2, 4))
    
    # Input on CUDA
    X_cuda = X_cpu.to(device)
    
    # Should work
    logits = model(X_cuda)
    assert logits.device.type == "cuda"
    
    # Sending CPU input to CUDA model should fail with normal PyTorch error
    with pytest.raises(RuntimeError):
        model(X_cpu)
