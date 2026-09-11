import os
import yaml
import subprocess
import shutil
import sys

def run_grid():
    base_config_path = "configs/default.yaml"
    temp_config_path = "configs/temp_bench.yaml"
    dataset_path = "data/datasets/zyra_dataset_v0.1.0"
    tokenizer_path = "mock_tokenizer_real"
    
    with open(base_config_path, "r") as f:
        base_config = yaml.safe_load(f)
        
    precisions = ["fp32", "amp"]
    batch_sizes = [1, 2, 4, 8]
    
    for prec in precisions:
        for bsz in batch_sizes:
            print(f"\n======================================")
            print(f"Running Benchmark: Precision={prec}, MicroBatch={bsz}")
            print(f"======================================")
            
            # modify config
            config = yaml.safe_load(yaml.dump(base_config)) # deep copy
            if "training" not in config:
                config["training"] = {}
            
            config["training"]["micro_batch_size"] = bsz
            config["training"]["precision"] = prec
            
            with open(temp_config_path, "w") as f:
                yaml.dump(config, f)
                
            cmd = [
                sys.executable, "scripts/benchmark_training.py",
                "--config", temp_config_path,
                "--dataset", dataset_path,
                "--tokenizer", tokenizer_path,
                "--benchmark-steps", "10"
            ]
            
            env = os.environ.copy()
            env["PYTHONPATH"] = os.path.abspath(".")
            result = subprocess.run(cmd, env=env)
            if result.returncode != 0:
                print(f"Error running benchmark for {prec} bsz {bsz}")
                
            # wait a bit for VRAM to clear
            import time
            time.sleep(2)

if __name__ == '__main__':
    run_grid()
