import pytest
import torch
import torch.nn as nn
from ai.brain.baseline_mlp import FixedContextMLP
from ai.training.reproducibility import set_seed

def test_overfit_tiny_dataset():
    """
    CRITICAL ACCEPTANCE TEST
    Ensures the model can memorize a tiny deterministic dataset and loss decreases significantly.
    """
    set_seed(1337)
    
    # 1. Setup Model
    vocab_size = 10
    config = {"context_length": 4, "embedding_dim": 32, "hidden_dim": 64, "dropout": 0.0}
    model = FixedContextMLP(config, vocab_size)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.01)
    criterion = nn.CrossEntropyLoss()
    
    # 2. Create deterministic tiny dataset (A B C D -> E)
    # Let's say: [0, 1, 2, 3] -> 4, [1, 2, 3, 4] -> 5
    X_train = torch.tensor([
        [0, 1, 2, 3],
        [1, 2, 3, 4],
        [2, 3, 4, 5],
        [3, 4, 5, 6]
    ], dtype=torch.long)
    
    Y_train = torch.tensor([4, 5, 6, 7], dtype=torch.long)
    
    # 3. Initial Forward Pass
    model.eval()
    with torch.no_grad():
        initial_logits = model(X_train)
        initial_loss = criterion(initial_logits, Y_train).item()
        
    # 4. Overfit Loop
    model.train()
    for step in range(100):
        optimizer.zero_grad()
        logits = model(X_train)
        loss = criterion(logits, Y_train)
        loss.backward()
        optimizer.step()
        
    # 5. Final Forward Pass
    model.eval()
    with torch.no_grad():
        final_logits = model(X_train)
        final_loss = criterion(final_logits, Y_train).item()
        
    # 6. Assertions
    assert final_loss < initial_loss, f"Loss did not decrease: {initial_loss} -> {final_loss}"
    assert final_loss < 0.1, f"Model failed to overfit tiny dataset, final loss is {final_loss}"
