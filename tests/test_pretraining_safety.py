import pytest
import torch
import torch.nn as nn
from unittest.mock import MagicMock
from ai.training.trainer import Trainer

def test_trainer_nan_protection():
    # Dummy model that returns NaN
    class BadModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.dummy = nn.Parameter(torch.zeros(1))
        def forward(self, x):
            return torch.full((x.size(0), x.size(1), 10), float('nan'))
            
    model = BadModel()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.1)
    
    # Dummy DatasetReader mock
    reader = MagicMock()
    # Return valid numpy arrays for batch
    import numpy as np
    reader.get_batch.return_value = (np.zeros((2, 10)), np.zeros((2, 10)))
    
    trainer = Trainer(
        model=model,
        optimizer=optimizer,
        train_config={"micro_batch_size": 2, "gradient_accumulation_steps": 1, "precision": "fp32"},
        dataset_reader=reader
    )
    
    # Train should raise ValueError for NaN
    with pytest.raises(ValueError, match="Loss is NaN or Inf"):
        trainer.train(sanity=True)
