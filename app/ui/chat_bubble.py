from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout
from PySide6.QtCore import Qt
import re

def parse_simple_markdown(text: str) -> str:
    # Escape HTML first
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    # Code blocks
    text = re.sub(r'```(?:.*?)\n(.*?)\n```', r'<pre style="background-color: #0a0a0a; color: #10b981; padding: 10px; border-radius: 6px; border: 1px solid #2f2f2f;">\1</pre>', text, flags=re.DOTALL)
    # Inline code
    text = re.sub(r'`(.*?)`', r'<code style="background-color: #2f2f2f; padding: 2px 4px; border-radius: 4px;">\1</code>', text)
    # Bold
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    # Italics
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    # Newlines
    text = text.replace('\n', '<br>')
    return text

class ChatBubbleWidget(QWidget):
    def __init__(self, role: str, content: str = ""):
        super().__init__()
        self.role = role
        self.raw_content = content
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 5, 0, 5)
        
        self.bubble_label = QLabel()
        self.bubble_label.setWordWrap(True)
        self.bubble_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        
        # Limit maximum width to avoid extremely long horizontal text
        self.bubble_label.setMaximumWidth(700)
        
        if role == "user":
            main_layout.addStretch()
            self.bubble_label.setStyleSheet("""
                QLabel {
                    background-color: #2563eb;
                    color: white;
                    padding: 12px 16px;
                    border-radius: 18px;
                    border-bottom-right-radius: 4px;
                    font-size: 14px;
                }
            """)
            self.bubble_label.setText(content)
            main_layout.addWidget(self.bubble_label)
        else:
            self.bubble_label.setStyleSheet("""
                QLabel {
                    background-color: #212121;
                    color: #f8fafc;
                    padding: 14px;
                    border-radius: 12px;
                    border: 1px solid #2f2f2f;
                    font-size: 14px;
                }
            """)
            main_layout.addWidget(self.bubble_label)
            main_layout.addStretch()
            self.update_content(content)

    def update_content(self, text: str):
        self.raw_content = text
        if self.role == "ai":
            parsed = parse_simple_markdown(text)
            self.bubble_label.setText(f"<div style='margin-bottom: 5px;'><b style='color: #38bdf8;'>ZYRA</b></div>{parsed}")
        else:
            self.bubble_label.setText(text)
