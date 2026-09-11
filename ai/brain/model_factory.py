from typing import Dict, Any
from .base_model import BaseLanguageModel
from .baseline_mlp import FixedContextMLP
from .transformer import MyAIDecoderTransformer

def create_model(config: Dict[str, Any], vocab_size: int) -> BaseLanguageModel:
    """
    Model factory to instantiate the correct architecture based on config.
    """
    arch = config.get("architecture", "my_ai_decoder_transformer")
    
    if arch == "fixed_context_mlp":
        return FixedContextMLP(config, vocab_size)
    elif arch == "my_ai_decoder_transformer":
        return MyAIDecoderTransformer(config, vocab_size)
    else:
        raise ValueError(f"Unknown architecture: {arch}")
