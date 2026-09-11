import pytest
import torch
import os
from ai.brain.baseline_mlp import FixedContextMLP
from ai.training.checkpoint import CheckpointManager

@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    return str(tmp_path / "checkpoints")

def test_checkpoint_save_load_equivalence(temp_checkpoint_dir):
    config = {"context_length": 4, "embedding_dim": 16, "hidden_dim": 32, "dropout": 0.0}
    vocab_size = 50
    
    # 1. Create original model and optimizer
    model_a = FixedContextMLP(config, vocab_size)
    opt_a = torch.optim.AdamW(model_a.parameters(), lr=0.1)
    
    # 2. Forward pass with dummy input
    X = torch.randint(0, vocab_size, (2, 4))
    model_a.eval()
    with torch.no_grad():
        logits_a = model_a(X)
        
    # 3. Save Checkpoint
    manager = CheckpointManager(temp_checkpoint_dir)
    manager.save(
        model=model_a,
        optimizer=opt_a,
        global_step=10,
        tokens_seen=40,
        train_config={"seed": 42},
        best_val_loss=0.5,
        tokenizer_fingerprint={"fingerprint_hash": "dummy_hash"}
    )
    
    cp_path = os.path.join(temp_checkpoint_dir, "step_00000010.pt")
    assert os.path.exists(cp_path)
    
    # 4. Load Checkpoint into a NEW model
    model_b = FixedContextMLP(config, vocab_size)
    opt_b = torch.optim.AdamW(model_b.parameters(), lr=0.1)
    
    manager.load(cp_path, model_b, opt_b, tokenizer_fingerprint={"fingerprint_hash": "dummy_hash"})
    
    # 5. Forward pass on new model with same input
    model_b.eval()
    with torch.no_grad():
        logits_b = model_b(X)
        
    # 6. Assert Equivalence
    assert torch.allclose(logits_a, logits_b, atol=1e-6), "Save/Load equivalence failed!"
    
def test_checkpoint_tokenizer_mismatch(temp_checkpoint_dir):
    config = {"context_length": 4, "embedding_dim": 16, "hidden_dim": 32, "dropout": 0.0}
    model = FixedContextMLP(config, vocab_size=50)
    opt = torch.optim.AdamW(model.parameters(), lr=0.1)
    
    manager = CheckpointManager(temp_checkpoint_dir)
    manager.save(
        model, opt, 10, 40, {}, 0.5, {"fingerprint_hash": "hash_1"}
    )
    
    cp_path = os.path.join(temp_checkpoint_dir, "step_00000010.pt")
    
    # Attempt load with different hash
    with pytest.raises(ValueError, match="Tokenizer fingerprint mismatch"):
        manager.load(cp_path, model, tokenizer_fingerprint={"fingerprint_hash": "hash_2"})
