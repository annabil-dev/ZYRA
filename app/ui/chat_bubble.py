from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout, QPushButton, QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
import re

def parse_simple_markdown(text: str) -> str:
    # Escape HTML first
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    # Inline code
    text = re.sub(r'`(.*?)`', r'<code style="background-color: #2f2f2f; padding: 2px 4px; border-radius: 4px; font-family: Consolas;">\1</code>', text)
    # Bold
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    # Italics
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    # Newlines
    text = text.replace('\n', '<br>')
    return text

class CodeBlockWidget(QWidget):
    def __init__(self, code: str, language: str = ""):
        super().__init__()
        self.code = code
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(0)
        
        # Header (Language + Copy Button)
        header = QWidget()
        header.setStyleSheet("background-color: #2f2f2f; border-top-left-radius: 6px; border-top-right-radius: 6px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 5, 10, 5)
        
        lang_lbl = QLabel(language if language else "code")
        lang_lbl.setStyleSheet("color: #a3a3a3; font-size: 12px; font-weight: bold; background: transparent;")
        
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setStyleSheet("""
            QPushButton { background-color: #3f3f3f; color: white; border: none; padding: 4px 10px; border-radius: 4px; font-size: 12px; }
            QPushButton:hover { background-color: #4f4f4f; }
        """)
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        
        h_layout.addWidget(lang_lbl)
        h_layout.addStretch()
        h_layout.addWidget(self.copy_btn)
        
        # Code content
        self.code_lbl = QLabel(code.strip())
        self.code_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # Avoid word wrap on code to keep formatting, unless it's too long
        self.code_lbl.setWordWrap(True)
        self.code_lbl.setFont(QFont("Consolas", 10))
        self.code_lbl.setStyleSheet("background-color: #0a0a0a; color: #10b981; padding: 10px; border-bottom-left-radius: 6px; border-bottom-right-radius: 6px; border: 1px solid #2f2f2f;")
        
        layout.addWidget(header)
        layout.addWidget(self.code_lbl)

    def copy_to_clipboard(self):
        QApplication.clipboard().setText(self.code.strip())
        self.copy_btn.setText("Copied!")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: self.copy_btn.setText("Copy"))

class ChatBubbleWidget(QWidget):
    def __init__(self, role: str, content: str = ""):
        super().__init__()
        self.role = role
        self.raw_content = content
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 5, 0, 5)
        
        self.bubble_container = QWidget()
        self.bubble_layout = QVBoxLayout(self.bubble_container)
        self.bubble_layout.setContentsMargins(14, 14, 14, 14)
        self.bubble_layout.setSpacing(5)
        
        # Limit maximum width
        self.bubble_container.setMaximumWidth(700)
        
        if role == "user":
            main_layout.addStretch()
            self.bubble_container.setStyleSheet("""
                QWidget {
                    background-color: #2563eb;
                    color: white;
                    border-radius: 18px;
                    border-bottom-right-radius: 4px;
                }
                QLabel { background: transparent; color: white; font-size: 14px; }
            """)
            lbl = QLabel(content)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.bubble_layout.addWidget(lbl)
            main_layout.addWidget(self.bubble_container)
        else:
            self.bubble_container.setStyleSheet("""
                QWidget {
                    background-color: #212121;
                    color: #f8fafc;
                    border-radius: 12px;
                    border: 1px solid #2f2f2f;
                }
                QLabel { background: transparent; color: #f8fafc; font-size: 14px; }
            """)
            main_layout.addWidget(self.bubble_container)
            main_layout.addStretch()
            self.update_content(content)

    def update_content(self, text: str):
        self.raw_content = text
        
        # Clear existing layout
        while self.bubble_layout.count():
            item = self.bubble_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        if self.role == "ai":
            header = QLabel("<div style='margin-bottom: 5px;'><b style='color: #38bdf8;'>ZYRA</b></div>")
            self.bubble_layout.addWidget(header)
            
            # Split by markdown code blocks
            parts = re.split(r'```(.*?)```', text, flags=re.DOTALL)
            
            for i, part in enumerate(parts):
                if not part.strip() and i % 2 == 0:
                    continue # Skip empty text blocks
                    
                if i % 2 == 0:
                    # Regular text
                    lbl = QLabel(parse_simple_markdown(part))
                    lbl.setWordWrap(True)
                    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    self.bubble_layout.addWidget(lbl)
                else:
                    # Code block
                    # The first line might be the language
                    lines = part.split('\n', 1)
                    lang = lines[0].strip() if len(lines) > 1 else ""
                    code = lines[1] if len(lines) > 1 else part
                    if not code.strip():
                        code = part
                        lang = ""
                    
                    code_widget = CodeBlockWidget(code, lang)
                    self.bubble_layout.addWidget(code_widget)
        else:
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.bubble_layout.addWidget(lbl)
