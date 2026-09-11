from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve

class Toast(QWidget):
    def __init__(self, parent, message, duration=5000, type="info"):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        
        # Strip HTML tags for clean toast display
        import re
        clean_text = re.sub(r'<[^>]+>', '', message)
        
        self.lbl = QLabel(clean_text)
        self.lbl.setStyleSheet("color: white; font-weight: bold; font-size: 13px; background: transparent;")
        
        bg_color = "#212121"
        if type == "info":
            border_color = "#3b82f6"
        elif type == "error":
            border_color = "#ef4444"
        elif type == "warning":
            border_color = "#f59e0b"
        elif type == "success":
            border_color = "#10b981"
        else:
            border_color = "#3b82f6"
            
        self.setStyleSheet(f"""
            Toast {{
                background-color: {bg_color};
                border: 1px solid #2f2f2f;
                border-left: 4px solid {border_color};
                border-radius: 8px;
            }}
        """)
        
        layout.addWidget(self.lbl)
        
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)
        
        self.duration = duration
        self.adjustSize()
        self.reposition()

    def reposition(self):
        if not self.parent():
            return
        parent_rect = self.parent().rect()
        x = parent_rect.width() - self.width() - 30
        y = 30
        self.move(x, y)

    def show_toast(self):
        self.show()
        self.raise_()
        self.reposition()
        
        self.anim_in = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_in.setDuration(300)
        self.anim_in.setStartValue(0.0)
        self.anim_in.setEndValue(1.0)
        self.anim_in.setEasingCurve(QEasingCurve.OutQuad)
        self.anim_in.start()
        
        QTimer.singleShot(self.duration, self.hide_toast)

    def hide_toast(self):
        self.anim_out = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_out.setDuration(300)
        self.anim_out.setStartValue(1.0)
        self.anim_out.setEndValue(0.0)
        self.anim_out.setEasingCurve(QEasingCurve.InQuad)
        self.anim_out.finished.connect(self.deleteLater)
        self.anim_out.start()
