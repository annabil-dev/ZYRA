import argparse
import yaml
from ai.brain.model_factory import create_model

def main():
    parser = argparse.ArgumentParser(description="Inspect Transformer Parameters")
    parser.add_argument("--config", type=str, default="configs/default.yaml", help="Path to config file")
    parser.add_argument("--profile", type=str, default="brain_v0_1", help="Model profile to inspect")
    parser.add_argument("--vocab-size", type=int, default=16384, help="Dummy vocab size for instantiation")
    
    args = parser.parse_args()
    
    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    profiles = config.get("model_profiles", {})
    if args.profile in profiles:
        model_config = profiles[args.profile]
    else:
        model_config = config.get("model", {})
        
    print(f"\nMY-AI Brain v0.1")
    print(f"Architecture:\n{model_config.get('architecture')}")
    print(f"\nVocabulary:\n{args.vocab_size}")
    print(f"\nContext:\n{model_config.get('context_length')}")
    print(f"\nLayers:\n{model_config.get('num_layers')}")
    print(f"\nHidden:\n{model_config.get('hidden_size')}")
    print(f"\nAttention Heads:\n{model_config.get('num_attention_heads')}")
    
    if "num_attention_heads" in model_config and "hidden_size" in model_config:
        print(f"\nHead Dimension:\n{model_config['hidden_size'] // model_config['num_attention_heads']}")
        
    print(f"\nIntermediate:\n{model_config.get('intermediate_size', model_config.get('hidden_size', 0) * 4)}") # Default logic if not set
    print(f"\nRoPE:\nenabled")
    print(f"\nRMSNorm:\nenabled")
    print(f"\nSwiGLU:\nenabled")
    print(f"\nWeight Tying:\n{'enabled' if model_config.get('tie_word_embeddings', True) else 'disabled'}")
    
    model = create_model(model_config, args.vocab_size)
    params = model.get_parameter_count()
    print(f"\nParameters:\n{params['total_parameters']:,} (Trainable: {params['trainable_parameters']:,})\n")
    
    print("Parameter Breakdown:")
    for name, module in model.named_children():
        mod_params = sum(p.numel() for p in module.parameters())
        print(f"{name}: {mod_params:,}")

if __name__ == "__main__":
    main()
