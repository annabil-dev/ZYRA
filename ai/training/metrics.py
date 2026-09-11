import time

class TrainingMetrics:
    """
    Tracks training performance and losses.
    """
    def __init__(self):
        self.start_time = time.time()
        self.total_tokens_processed = 0
        self.losses = []
        self._step_start_time = time.time()
        
    def log_step(self, loss: float, tokens_in_batch: int):
        self.losses.append(loss)
        self.total_tokens_processed += tokens_in_batch
        
    def get_average_loss(self, window: int = 100) -> float:
        if not self.losses:
            return 0.0
        recent = self.losses[-window:]
        return sum(recent) / len(recent)
        
    def get_throughput(self, elapsed_seconds: float) -> float:
        """Returns tokens per second."""
        if elapsed_seconds <= 0:
            return 0.0
        return self.total_tokens_processed / elapsed_seconds
