import pytest
import torch
import torch.nn as nn
from copy import deepcopy
from ai.brain.baseline_mlp import FixedContextMLP
from ai.training.reproducibility import set_seed

def test_gradient_update():
    set_seed(42)
    config = {"context_length": 4, "embedding_dim": 16, "hidden_dim": 32, "dropout": 0.0}
    model = FixedContextMLP(config, vocab_size=50)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.1)
    criterion = nn.CrossEntropyLoss()
    
    # Store copy of initial weights
    initial_weights = {name: p.clone().detach() for name, p in model.named_parameters()}
    
    # Dummy input
    X = torch.randint(0, 50, (2, 4))
    # Dummy target
    Y = torch.randint(0, 50, (2,))
    
    # Forward
    model.train()
    logits = model(X)
    loss = criterion(logits, Y)
    
    # Assert loss is finite
    assert torch.isfinite(loss)
    
    # Backward
    optimizer.zero_grad()
    loss.backward()
    
    # Assert gradients exist and are not zero
    has_grad = False
    for name, p in model.named_parameters():
        assert p.grad is not None, f"Parameter {name} has no gradient"
        if p.grad.abs().sum() > 0:
            has_grad = True
    assert has_grad, "All gradients are zero"
    
    # Optimizer step
    optimizer.step()
    
    # Assert weights changed
    weights_changed = False
    for name, p in model.named_parameters():
        if not torch.allclose(initial_weights[name], p):
            weights_changed = True
            break
            
    assert weights_changed, "Optimizer step did not change any weights"
