from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

class PlaceholderPage(QWidget):
    def __init__(self, title: str):
        super().__init__()
        layout = QVBoxLayout(self)
        
        label = QLabel(f"{title}\n(Coming Soon)")
        label.setAlignment(Qt.AlignCenter)
        
        # Styling placeholder
        label.setStyleSheet("font-size: 24px; color: #585b70; font-weight: bold;")
        layout.addWidget(label)
