from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

class SettingsPage(QWidget):
    def __init__(self, chat_page):
        super().__init__()
        self.chat_page = chat_page
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.setContentsMargins(40, 40, 40, 40)
        
        header = QLabel("Settings")
        header.setStyleSheet("font-size: 28px; font-weight: bold; color: white; margin-bottom: 20px;")
        layout.addWidget(header)
        
        # Take the settings widget from chat_page
        layout.addWidget(self.chat_page.settings_widget)
        
        layout.addStretch()
