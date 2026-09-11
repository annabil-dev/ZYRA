import pytest
import torch
import torch.nn as nn
from ai.brain.transformer import MyAIDecoderTransformer
from ai.training.reproducibility import set_seed

def test_transformer_tiny_overfit():
    """
    CRITICAL ACCEPTANCE TEST for Transformer.
    Ensures the entire causal pipeline can memorize a deterministic dataset.
    """
    set_seed(1337)
    
    vocab_size = 10
    config = {
        "context_length": 8,
        "hidden_size": 32,
        "num_layers": 2,
        "num_attention_heads": 4,
        "intermediate_size": 64,
        "tie_word_embeddings": True
    }
    
    model = MyAIDecoderTransformer(config, vocab_size)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.01)
    criterion = nn.CrossEntropyLoss()
    
    # Sequence: 0 1 2 3 4 5 6 7 8 9
    # For causal LM, given sequence X (length T), targets are X shifted by 1.
    # Let's create a single sequence of length 9: [0, 1, 2, 3, 4, 5, 6, 7, 8]
    # Input: [0, 1, 2, 3, 4, 5, 6, 7]
    # Target: [1, 2, 3, 4, 5, 6, 7, 8]
    seq = torch.tensor([[0, 1, 2, 3, 4, 5, 6, 7, 8]], dtype=torch.long)
    X_train = seq[:, :-1]
    Y_train = seq[:, 1:]
    
    # Initial loss
    model.eval()
    with torch.no_grad():
        initial_logits = model(X_train)
        initial_loss = criterion(initial_logits.view(-1, vocab_size), Y_train.view(-1)).item()
        
    # Overfit loop
    model.train()
    for step in range(200):
        optimizer.zero_grad()
        logits = model(X_train)
        loss = criterion(logits.view(-1, vocab_size), Y_train.view(-1))
        loss.backward()
        optimizer.step()
        
    # Final loss
    model.eval()
    with torch.no_grad():
        final_logits = model(X_train)
        final_loss = criterion(final_logits.view(-1, vocab_size), Y_train.view(-1)).item()
        
    assert final_loss < initial_loss, f"Transformer failed to learn, loss did not decrease: {initial_loss} -> {final_loss}"
    assert final_loss < 0.1, f"Transformer failed to overfit tiny dataset, final loss is {final_loss}"
