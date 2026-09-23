import sys
import logging
from PySide6.QtWidgets import QApplication
from app.core.config import ConfigManager
from app.core.paths import PathManager
from app.core.hardware import HardwareDetector
from app.core.logging_service import LoggingService
from app.core.database import DatabaseManager
from app.ui.main_window import MainWindow

class Application:
    """Core application wrapper."""
    def __init__(self, argv):
        self.app = QApplication(argv)
        
        # Setup Core Services
        import os
        import sys
        if getattr(sys, 'frozen', False):
            bundle_dir = sys._MEIPASS
            # Use %APPDATA%\ZYRA AI so we have write permissions
            user_data_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ZYRA AI")
        else:
            bundle_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            user_data_dir = bundle_dir
            
        config_path = os.path.join(bundle_dir, "configs", "default.yaml")
        self.config = ConfigManager(config_path)
        self.path_manager = PathManager(self.config, base_dir=user_data_dir)
        
        log_dir = self.path_manager.get_path("logs")
        self.logging_service = LoggingService(log_dir)
        self.logger = self.logging_service.get_logger("application")
        
        self.logger.info("Initializing MY-AI application...")
        
        db_dir = self.path_manager.get_path("database")
        self.db_manager = DatabaseManager(db_dir, self.logging_service.get_logger("database"))
        
        # Detect Hardware
        self.logger.info("Detecting hardware...")
        self.hardware_info = HardwareDetector.get_hardware_info()
        self.logger.info(f"Hardware detected: {self.hardware_info}")
        
        # Initialize GUI
        self.logger.info("Initializing UI...")
        
        # Load Stylesheet
        import os
        qss_path = os.path.join(os.path.dirname(__file__), "ui", "style.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                self.app.setStyleSheet(f.read())
                
        self.main_window = MainWindow(self.hardware_info, self.logging_service.log_file, self.db_manager)
        
        # Start P2P Node in background
        self.logger.info("Starting P2P Gossip Node...")
        import threading
        import asyncio
        from p2p.network import P2PNode
        
        # Use fixed port 5001 by default, or read from env
        import os
        p2p_port = int(os.environ.get("P2P_PORT", 5001))
        self.p2p_node = P2PNode(port=p2p_port)
        
        def run_p2p():
            asyncio.run(self.p2p_node.start())
            
        self.p2p_thread = threading.Thread(target=run_p2p, daemon=True)
        self.p2p_thread.start()
        
        # Make p2p_node accessible to MainWindow/Workers
        self.main_window.p2p_node = self.p2p_node
        
    def run(self):
        """Runs the QApplication event loop."""
        self.main_window.show()
        self.logger.info("MY-AI started.")
        
        exit_code = self.app.exec()
        
        self.logger.info("MY-AI shutting down...")
        self.db_manager.close()
        return exit_code
