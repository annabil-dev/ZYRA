import pytest
import torch
import torch.nn as nn
from ai.training.scheduler import get_cosine_schedule_with_warmup

def test_scheduler_warmup_cosine():
    model = nn.Linear(10, 2)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.1)
    
    # 2 steps warmup, 10 steps total, min lr ratio 0.1
    scheduler = get_cosine_schedule_with_warmup(
        optimizer, num_warmup_steps=2, num_training_steps=10, min_lr_ratio=0.1
    )
    
    lrs = []
    for _ in range(11):
        lrs.append(scheduler.get_last_lr()[0])
        optimizer.step()
        scheduler.step()
        
    # Warmup
    assert lrs[0] == 0.0 # Step 0
    assert lrs[1] == 0.05 # Step 1 (0.5 * 0.1)
    
    # Peak
    assert lrs[2] == 0.1 # Step 2
    
    # Decay
    assert lrs[-1] < lrs[2]
    
    # Final LR should be exactly 0.01 at step 10
    assert abs(lrs[10] - 0.01) < 1e-5
