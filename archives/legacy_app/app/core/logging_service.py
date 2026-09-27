import logging
import os
from datetime import datetime

class LoggingService:
    """Central logging service for the application."""
    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        
        # We use a date-stamped file name
        date_str = datetime.now().strftime("%Y-%m-%d")
        self.log_file = os.path.join(self.log_dir, f"my_ai_{date_str}.log")
        
        self._setup_logger()

    def _setup_logger(self) -> None:
        self.logger = logging.getLogger("MY-AI")
        self.logger.setLevel(logging.DEBUG)
        
        # Avoid duplicate handlers if re-initialized
        if not self.logger.handlers:
            formatter = logging.Formatter(
                '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            
            # File handler
            file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)

    def get_logger(self, module_name: str) -> logging.Logger:
        """Returns a child logger for a specific module."""
        return self.logger.getChild(module_name)
