import json
import torch
import gc
from ai.tokenizer.tokenizer import MyAITokenizer
from ai.dataset.metadata import DatasetMetadata
from ai.brain.model_factory import create_model

def get_vram_info():
    if not torch.cuda.is_available():
        return {"allocated": 0, "reserved": 0, "total": 0}
    t = torch.cuda.get_device_properties(0).total_memory
    r = torch.cuda.memory_reserved(0)
    a = torch.cuda.memory_allocated(0)
    return {"allocated": a, "reserved": r, "total": t}

def main():
    print("--- GPU HARDWARE VERIFICATION ---")
    cuda_av = torch.cuda.is_available()
    print(f"CUDA availability: {cuda_av}")
    if cuda_av:
        print(f"GPU name: {torch.cuda.get_device_name(0)}")
        print(f"CUDA runtime: {torch.version.cuda}")
    print(f"PyTorch version: {torch.__version__}")
    
    vram = get_vram_info()
    print(f"Total VRAM: {vram['total'] / (1024**3):.2f} GB")
    print(f"VRAM allocated: {vram['allocated'] / (1024**2):.2f} MB")
    print(f"VRAM reserved: {vram['reserved'] / (1024**2):.2f} MB")
    
    print("\n--- TOKENIZER ARTIFACT METADATA ---")
    try:
        tokenizer = MyAITokenizer.load("models/ZYRA/Tokenizer/v1.0.0")
        print("Tokenizer v1.0.0 exists.")
        print(f"Vocab size: {tokenizer.vocab.size()}")
        # Check special tokens from config
        st = tokenizer.config.get("special_tokens", {})
        print(f"Special token IDs: {st}")
        # Explicitly check for pad, bos, eos, unk
        print(f"Has <|pad|>? {'<|pad|>' in st.values() or '<|pad|>' in st.keys()}")
        print(f"Has <|bos|>? {'<|bos|>' in st.values() or '<|bos|>' in st.keys()}")
        print(f"Has <|eos|>? {'<|eos|>' in st.values() or '<|eos|>' in st.keys()}")
        print(f"Has <|unk|>? {'<|unk|>' in st.values() or '<|unk|>' in st.keys()}")
        
        # We need the actual manifest since fingerprint method might not exist in phase 1 codebase
        with open("models/ZYRA/Tokenizer/v1.0.0/tokenizer_manifest.json", "r") as f:
            manifest = json.load(f)
            print(f"Vocab hash: {manifest.get('vocab_hash')}")
            print(f"Merges hash: {manifest.get('merges_hash')}")
            print(f"Tokenizer fingerprint (from manifest if exists): {manifest.get('fingerprint', 'NOT RECORDED IN MANIFEST')}")
    except Exception as e:
        print(f"Tokenizer Load Error: {e}")

    print("\n--- DATASET METADATA ---")
    try:
        ds_metadata = DatasetMetadata.load("data/datasets/zyra_dataset_v0.1.0")
        print(f"Dataset dtype: {ds_metadata.get('dtype')}")
        ds_tok_fp = ds_metadata.get("tokenizer_fingerprint", {})
        print(f"Dataset tokenizer fingerprint name: {ds_tok_fp.get('name')}")
        print(f"Dataset tokenizer vocab_hash: {ds_tok_fp.get('vocab_hash')}")
        # Actual dataset fingerprint
        print(f"Dataset fingerprint (self-hash if exists): {ds_metadata.get('fingerprint', 'Derives from tokenizer_fingerprint')}")
    except Exception as e:
        print(f"Dataset Metadata Error: {e}")

    print("\n--- RUNTIME PARAMETER COUNT ---")
    try:
        config = {
            "context_length": 256,
            "hidden_size": 256,
            "num_layers": 12,
            "num_attention_heads": 8,
            "intermediate_size": 1024,
            "tie_word_embeddings": True
        }
        # Wait, the prompt says "Expected previous report: 35,660,288"
        # Let's load the actual configs/training/zyra_1_pretrain_dev.yaml to see what it is
        import yaml
        with open("configs/training/zyra_1_pretrain_dev.yaml", "r") as f:
            yaml_cfg = yaml.safe_load(f)
            arch_cfg = yaml_cfg.get("architecture", {})
            print(f"Loaded config from YAML: {arch_cfg}")
            
        model = create_model(arch_cfg, 16384)
        total_params = sum(p.numel() for p in model.parameters())
        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        print(f"Architecture: my_ai_decoder_transformer v1")
        print(f"Total parameters: {total_params:,}")
        print(f"Trainable parameters: {trainable_params:,}")
    except Exception as e:
        print(f"Model Load Error: {e}")

if __name__ == '__main__':
    main()
