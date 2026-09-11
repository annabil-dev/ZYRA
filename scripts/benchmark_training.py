import argparse
import yaml
import logging
import torch
import time
import psutil
import os

from ai.tokenizer import MyAITokenizer
from ai.dataset.reader import DatasetReader
from ai.brain.model_factory import create_model

def get_vram_usage():
    if not torch.cuda.is_available():
        return 0, 0
    alloc = torch.cuda.memory_allocated() / (1024**2)
    res = torch.cuda.memory_reserved() / (1024**2)
    return alloc, res

def main():
    parser = argparse.ArgumentParser(description="Benchmark ZYRA Pretraining on RTX 4060")
    parser.add_argument("--config", type=str, required=True, help="Path to pretraining config file")
    parser.add_argument("--dataset", type=str, required=True, help="Path to dataset")
    parser.add_argument("--tokenizer", type=str, required=True, help="Path to tokenizer")
    parser.add_argument("--benchmark-steps", type=int, default=10, help="Number of micro-batches to benchmark")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    logger = logging.getLogger("benchmark")
    logger.info("Initializing VRAM & Throughput Benchmark...")
    
    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    arch_config = config.get("architecture", {})
    train_config = config.get("training", {})
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        logger.warning("CUDA not available. Benchmark results will represent CPU.")
    
    logger.info(f"Target Device: {device}")
    
    tokenizer = MyAITokenizer.load(args.tokenizer)
    vocab_size = 16384 # Hardcoded to match zyra_dataset_v0.1.0 to prevent CUDA OOB
    reader = DatasetReader(args.dataset, tokenizer)
    
    context_length = arch_config.get("context_length", 256)
    micro_batch = train_config.get("micro_batch_size", 4)
    use_amp = train_config.get("precision", "auto") == "amp" and device.type == "cuda"
    
    logger.info("Loading Model (this allocates initial VRAM)...")
    model = create_model(arch_config, vocab_size).to(device)
    params = model.get_parameter_count()['total_parameters']
    
    a1, r1 = get_vram_usage()
    logger.info(f"VRAM after Model Load - Allocated: {a1:.0f}MB, Reserved: {r1:.0f}MB")
    
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.0003)
    criterion = torch.nn.CrossEntropyLoss()
    scaler = torch.amp.GradScaler(enabled=use_amp)
    
    logger.info(f"\n--- BENCHMARK SETTINGS ---")
    logger.info(f"Parameters   : {params:,}")
    logger.info(f"Precision    : {'AMP (FP16/BF16)' if use_amp else 'FP32'}")
    logger.info(f"Context Len  : {context_length}")
    logger.info(f"Micro Batch  : {micro_batch}")
    logger.info(f"Tokens/Step  : {context_length * micro_batch}")
    
    # Warmup
    logger.info("\nRunning Warmup (1 step)...")
    model.train()
    try:
        X_np, Y_np = reader.get_batch("train", micro_batch, context_length)
        X = torch.from_numpy(X_np).long().to(device)
        Y = torch.from_numpy(Y_np).long().to(device)
        
        optimizer.zero_grad()
        with torch.amp.autocast(device_type=device.type, enabled=use_amp):
            logits = model(X)
            loss = criterion(logits.view(-1, vocab_size), Y.view(-1))
            
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        
    except Exception as e:
        logger.error(f"OOM or Error during warmup: {e}")
        return
        
    a2, r2 = get_vram_usage()
    logger.info(f"VRAM after Warmup (Optimizer States initialized) - Allocated: {a2:.0f}MB, Reserved: {r2:.0f}MB")
    
    # Benchmark
    logger.info(f"\nRunning Benchmark ({args.benchmark_steps} steps)...")
    if device.type == "cuda":
        torch.cuda.synchronize()
    start_time = time.time()
    
    peak_alloc = a2
    peak_res = r2
    
    for i in range(args.benchmark_steps):
        X_np, Y_np = reader.get_batch("train", micro_batch, context_length)
        X = torch.from_numpy(X_np).long().to(device)
        Y = torch.from_numpy(Y_np).long().to(device)
        
        optimizer.zero_grad()
        # autocast for CPU bfloat16 is supported, but let's keep it safe
        with torch.amp.autocast(device_type=device.type, enabled=use_amp):
            logits = model(X)
            loss = criterion(logits.view(-1, vocab_size), Y.view(-1))
            
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        
        ca, cr = get_vram_usage()
        if ca > peak_alloc: peak_alloc = ca
        if cr > peak_res: peak_res = cr
        
    if device.type == "cuda":
        torch.cuda.synchronize()
    total_time = time.time() - start_time
    
    total_tokens = args.benchmark_steps * micro_batch * context_length
    tok_per_sec = total_tokens / total_time
    step_time = total_time / args.benchmark_steps
    
    ram_usage = psutil.Process(os.getpid()).memory_info().rss / (1024**2)
    
    logger.info("\n=== RTX 4060 8GB BENCHMARK RESULTS ===")
    logger.info(f"Avg Step Time     : {step_time*1000:.1f} ms")
    logger.info(f"Throughput        : {tok_per_sec:.0f} tokens / second")
    logger.info(f"Peak VRAM Alloc   : {peak_alloc:.0f} MB")
    logger.info(f"Peak VRAM Reserved: {peak_res:.0f} MB")
    logger.info(f"System RAM Usage  : {ram_usage:.0f} MB")
    
    headroom = 8192 - peak_res
    if headroom < 512:
        logger.warning(f"DANGER: Very low VRAM headroom ({headroom:.0f} MB)! Reduce micro_batch_size or context_length.")
    else:
        logger.info(f"VRAM Headroom     : {headroom:.0f} MB (Safe)")
    
if __name__ == "__main__":
    main()
