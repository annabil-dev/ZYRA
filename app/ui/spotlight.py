from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QApplication, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent

class SpotlightWidget(QWidget):
    submitted = Signal(str)

    def __init__(self):
        super().__init__()
        
        # Frameless, stays on top, tool window (hides from taskbar usually)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setFixedSize(700, 100)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Tanya ZYRA apa saja...")
        font = QFont("Segoe UI", 16)
        self.input_field.setFont(font)
        
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #0f172a;
                color: #f8fafc;
                border: 2px solid #3b82f6;
                border-radius: 12px;
                padding: 15px;
            }
        """)
        
        # Add shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 5)
        self.input_field.setGraphicsEffect(shadow)
        
        self.layout.addWidget(self.input_field)
        
        self.input_field.returnPressed.connect(self.on_submit)
        
    def center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 3  # A bit higher than center
        self.move(x, y)
        
    def show_and_focus(self):
        self.center_on_screen()
        self.input_field.clear()
        self.show()
        self.activateWindow()
        self.input_field.setFocus()
        
    def on_submit(self):
        text = self.input_field.text().strip()
        if text:
            self.submitted.emit(text)
        self.hide()
        
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
