import pytest
import torch
from ai.brain.transformer import MyAIDecoderTransformer

def test_weight_tying():
    config = {
        "context_length": 8,
        "hidden_size": 32,
        "num_layers": 1,
        "num_attention_heads": 2,
        "intermediate_size": 64,
        "tie_word_embeddings": True
    }
    
    model = MyAIDecoderTransformer(config, vocab_size=100)
    
    # Check if the memory pointers are exactly the same
    assert model.token_embedding.weight.data_ptr() == model.lm_head.weight.data_ptr()
    
    # If tie_word_embeddings is False, they should not be the same
    config["tie_word_embeddings"] = False
    model_untied = MyAIDecoderTransformer(config, vocab_size=100)
    assert model_untied.token_embedding.weight.data_ptr() != model_untied.lm_head.weight.data_ptr()
