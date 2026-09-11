from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt
import os

class LogsPage(QWidget):
    def __init__(self, log_file_path: str):
        super().__init__()
        self.log_file_path = log_file_path
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setObjectName("Terminal")
        
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh Logs")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self.load_logs)
        btn_layout.addStretch()
        btn_layout.addWidget(refresh_btn)
        
        layout.addWidget(self.log_viewer)
        layout.addLayout(btn_layout)
        
        self.load_logs()

    def load_logs(self):
        """Reloads the logs from the file."""
        if os.path.exists(self.log_file_path):
            with open(self.log_file_path, "r", encoding="utf-8") as file:
                self.log_viewer.setPlainText(file.read())
            self.log_viewer.verticalScrollBar().setValue(self.log_viewer.verticalScrollBar().maximum())
        else:
            self.log_viewer.setPlainText("Log file not found.")
