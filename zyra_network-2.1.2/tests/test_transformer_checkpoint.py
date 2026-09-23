import pytest
import torch
import os
from ai.brain.transformer import MyAIDecoderTransformer
from ai.training.checkpoint import CheckpointManager

@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    return str(tmp_path / "checkpoints_transformer")

def test_transformer_checkpoint_save_load_equivalence(temp_checkpoint_dir):
    config = {
        "context_length": 8,
        "hidden_size": 32,
        "num_layers": 2,
        "num_attention_heads": 4,
        "intermediate_size": 64,
        "tie_word_embeddings": True
    }
    vocab_size = 50
    
    model_a = MyAIDecoderTransformer(config, vocab_size)
    model_a.eval()
    opt_a = torch.optim.AdamW(model_a.parameters(), lr=0.1)
    
    X = torch.randint(0, vocab_size, (2, 8))
    with torch.no_grad():
        logits_a = model_a(X)
        
    manager = CheckpointManager(temp_checkpoint_dir)
    manager.save(
        model=model_a,
        optimizer=opt_a,
        global_step=10,
        tokens_seen=80,
        train_config={"seed": 42},
        best_val_loss=0.5,
        tokenizer_fingerprint={"fingerprint_hash": "hash_t"}
    )
    
    cp_path = os.path.join(temp_checkpoint_dir, "step_00000010.pt")
    
    model_b = MyAIDecoderTransformer(config, vocab_size)
    model_b.eval()
    opt_b = torch.optim.AdamW(model_b.parameters(), lr=0.1)
    
    manager.load(cp_path, model_b, opt_b, tokenizer_fingerprint={"fingerprint_hash": "hash_t"})
    
    with torch.no_grad():
        logits_b = model_b(X)
        
    assert torch.allclose(logits_a, logits_b, atol=1e-6), "Transformer Save/Load equivalence failed!"
