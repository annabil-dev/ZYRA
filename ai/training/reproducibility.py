import random
import numpy as np
import torch
import logging

def set_seed(seed: int = 1337) -> None:
    """
    Sets the random seed for all components to ensure deterministic behavior.
    """
    logger = logging.getLogger("training")
    logger.info(f"Setting global seed to {seed}")
    
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        
    # To ensure fully deterministic behavior on CUDA
    # Note: This might reduce performance on some operations
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
