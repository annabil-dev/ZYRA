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
        
        # Take the settings widget from chat_page and widen it
        self.chat_page.settings_widget.setFixedWidth(400)
        layout.addWidget(self.chat_page.settings_widget)
        
        layout.addStretch()
        
        # Display current version at the bottom
        import os, sys, json
        user_data_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ZYRA AI")
        current_version = "v1.0.14" # base
        current_v_path = os.path.join(user_data_dir, "current_version.json")
        if os.path.exists(current_v_path):
            try:
                with open(current_v_path, 'r') as f:
                    current_version = json.load(f).get("version", "v1.0.14")
            except Exception:
                pass
                
        version_lbl = QLabel(f"ZYRA Version: {current_version}")
        version_lbl.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(version_lbl, alignment=Qt.AlignCenter)
