from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout, QPushButton, QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
import re

def highlight_universal_code(code: str, language: str) -> str:
    import pygments
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.formatters import HtmlFormatter
    from pygments.util import ClassNotFound
    
    code = code.strip()
    if not code:
        return ""
        
    try:
        if language:
            lexer = get_lexer_by_name(language, stripall=True)
        else:
            lexer = guess_lexer(code)
    except ClassNotFound:
        from pygments.lexers.special import TextLexer
        lexer = TextLexer()
        
    # We use noclasses=True to generate inline CSS styles which QLabel/QTextBrowser can render
    # 'one-dark' is a popular VSCode-like dark theme
    formatter = HtmlFormatter(style="one-dark", noclasses=True, cssclass="", prestyles="margin: 0; padding: 0;")
    highlighted = pygments.highlight(code, lexer, formatter)
    
    # Remove the surrounding <div class=""><pre>...</pre></div> wrapper that Pygments adds, 
    # because we want to inject it inside our QLabel directly with our own formatting.
    # Pygments usually outputs: <div ...><pre style="...">code</pre></div>
    
    # Extract just the content inside <pre>...</pre>
    match = re.search(r'<pre[^>]*>(.*?)</pre>', highlighted, flags=re.DOTALL)
    if match:
        content = match.group(1)
        # Convert newlines to <br> for QLabel
        return content.replace('\n', '<br>')
        
    return highlighted.replace('\n', '<br>')

def parse_simple_markdown(text: str) -> str:
    # Escape HTML first
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    # Inline code
    text = re.sub(r'`(.*?)`', r'<code style="background-color: #2f2f2f; padding: 2px 4px; border-radius: 4px; font-family: Consolas; color: #e5c07b;">\1</code>', text)
    # Bold
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    # Italics
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    
    # Simple unordered lists (bullet points)
    # Replace lines starting with "- " or "* " with <li>
    lines = text.split('\n')
    in_list = False
    result_lines = []
    
    for line in lines:
        match = re.match(r'^\s*[\-\*]\s+(.*)', line)
        if match:
            if not in_list:
                result_lines.append('<ul style="margin-top: 4px; margin-bottom: 4px; padding-left: 20px;">')
                in_list = True
            result_lines.append(f'<li>{match.group(1)}</li>')
        else:
            if in_list:
                result_lines.append('</ul>')
                in_list = False
            result_lines.append(line)
            
    if in_list:
        result_lines.append('</ul>')
        
    # Join and replace remaining newlines (not inside ul/li) with <br>
    # To avoid <br> between <li> tags, we join with \n then selectively replace.
    joined = '\n'.join(result_lines)
    # A bit hacky but works for QLabel: replace \n with <br> unless it's adjacent to block tags
    joined = re.sub(r'(?<!>)\n', '<br>', joined)
    joined = joined.replace('\n', '') # Remove remaining newlines to prevent weird spacing in QLabel
    
    return joined

class CodeBlockWidget(QWidget):
    def __init__(self, code: str = "", language: str = ""):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(0)
        
        # Header (Language + Copy Button)
        self.header = QWidget()
        self.header.setStyleSheet("background-color: #2f2f2f; border-top-left-radius: 6px; border-top-right-radius: 6px; border: none;")
        h_layout = QHBoxLayout(self.header)
        h_layout.setContentsMargins(10, 5, 10, 5)
        
        self.lang_lbl = QLabel(language if language else "code")
        self.lang_lbl.setStyleSheet("color: #a3a3a3; font-size: 12px; font-weight: bold; background: transparent; border: none;")
        
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setStyleSheet("""
            QPushButton { background-color: #3f3f3f; color: white; border: none; padding: 4px 10px; border-radius: 4px; font-size: 12px; }
            QPushButton:hover { background-color: #4f4f4f; }
        """)
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        
        self.download_btn = QPushButton("Download")
        self.download_btn.setCursor(Qt.PointingHandCursor)
        self.download_btn.setStyleSheet("""
            QPushButton { background-color: #3f3f3f; color: white; border: none; padding: 4px 10px; border-radius: 4px; font-size: 12px; margin-left: 5px; }
            QPushButton:hover { background-color: #4f4f4f; }
        """)
        self.download_btn.clicked.connect(self.download_file)
        
        h_layout.addWidget(self.lang_lbl)
        h_layout.addStretch()
        h_layout.addWidget(self.download_btn)
        h_layout.addWidget(self.copy_btn)
        
        # Code content
        self.code_lbl = QLabel()
        self.code_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.code_lbl.setWordWrap(True)
        self.code_lbl.setFont(QFont("Consolas", 10))
        self.code_lbl.setStyleSheet("background-color: #1e1e1e; color: #abb2bf; padding: 10px; border-bottom-left-radius: 6px; border-bottom-right-radius: 6px; border: 1px solid #2f2f2f;")
        
        layout.addWidget(self.header)
        layout.addWidget(self.code_lbl)
        
        self.raw_code = code
        self.language = language
        self.update_code(code, language)

    def update_code(self, code: str, language: str):
        self.raw_code = code
        self.language = language
        self.lang_lbl.setText(language if language else "code")
        
        # Use pygments for all languages
        highlighted = highlight_universal_code(code.strip(), language)
        self.code_lbl.setText(highlighted)

    def download_file(self):
        from PySide6.QtWidgets import QFileDialog
        
        # Determine extension based on language
        ext_map = {
            "python": ".py", "javascript": ".js", "html": ".html", "css": ".css",
            "c": ".c", "cpp": ".cpp", "java": ".java", "json": ".json",
            "markdown": ".md", "bash": ".sh", "sh": ".sh"
        }
        lang = self.language.lower()
        ext = ext_map.get(lang, ".txt")
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Download File", f"code{ext}", f"All Files (*.*)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.raw_code.strip())
                
                self.download_btn.setText("Saved!")
                from PySide6.QtCore import QTimer
                QTimer.singleShot(2000, lambda: self.download_btn.setText("Download"))
            except Exception as e:
                self.download_btn.setText("Error")

    def copy_to_clipboard(self):
        QApplication.clipboard().setText(self.raw_code.strip())
        self.copy_btn.setText("Copied!")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: self.copy_btn.setText("Copy"))

class ChatBubbleWidget(QWidget):
    def __init__(self, role: str, content: str = ""):
        super().__init__()
        self.role = role
        self.raw_content = content
        
        self._part_widgets = []
        self._part_types = []
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 5, 0, 5)
        
        self.bubble_container = QWidget()
        self.bubble_container.setObjectName("BubbleContainer")
        self.bubble_layout = QVBoxLayout(self.bubble_container)
        self.bubble_layout.setContentsMargins(14, 14, 14, 14)
        self.bubble_layout.setSpacing(5)
        
        # Limit maximum width
        self.bubble_container.setMaximumWidth(700)
        
        if role == "user":
            main_layout.addStretch()
            self.bubble_container.setStyleSheet("""
                #BubbleContainer {
                    background-color: #2563eb;
                    border-radius: 18px;
                    border-bottom-right-radius: 4px;
                }
            """)
            lbl = QLabel(content)
            lbl.setStyleSheet("background: transparent; color: white; font-size: 14px; border: none;")
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.bubble_layout.addWidget(lbl)
            main_layout.addWidget(self.bubble_container)
        else:
            self.bubble_container.setStyleSheet("""
                #BubbleContainer {
                    background-color: #212121;
                    border-radius: 12px;
                    border: 1px solid #2f2f2f;
                }
            """)
            main_layout.addWidget(self.bubble_container)
            main_layout.addStretch()
            self.update_content(content)

    def update_content(self, text: str):
        self.raw_content = text
                
        if self.role == "ai":
            # Split by markdown code blocks
            parts = re.split(r'```(.*?)```', text, flags=re.DOTALL)
            
            clean_parts = []
            for i, part in enumerate(parts):
                if not part.strip() and i % 2 == 0:
                    continue
                clean_parts.append((i % 2 == 1, part))
                
            # Check if we need to rebuild the layout structure
            rebuild = False
            if len(clean_parts) != len(self._part_widgets):
                rebuild = True
            else:
                for j, (is_code, _) in enumerate(clean_parts):
                    if is_code != self._part_types[j]:
                        rebuild = True
                        break
                        
            if rebuild:
                # Clear existing layout safely
                while self.bubble_layout.count():
                    item = self.bubble_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()
                
                self._part_widgets = []
                self._part_types = []
                
                header = QLabel("<div style='margin-bottom: 5px;'><b style='color: #38bdf8;'>ZYRA</b></div>")
                header.setStyleSheet("border: none; background: transparent;")
                self.bubble_layout.addWidget(header)
                
                for is_code, part in clean_parts:
                    if not is_code:
                        lbl = QLabel()
                        lbl.setWordWrap(True)
                        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
                        lbl.setStyleSheet("background: transparent; color: #f8fafc; font-size: 14px; border: none;")
                        self.bubble_layout.addWidget(lbl)
                        self._part_widgets.append(lbl)
                        self._part_types.append(False)
                    else:
                        code_widget = CodeBlockWidget("", "")
                        self.bubble_layout.addWidget(code_widget)
                        self._part_widgets.append(code_widget)
                        self._part_types.append(True)
            
            # Fast stateful update
            for j, (is_code, part) in enumerate(clean_parts):
                widget = self._part_widgets[j]
                if not is_code:
                    widget.setText(parse_simple_markdown(part))
                else:
                    lines = part.split('\n', 1)
                    lang = lines[0].strip() if len(lines) > 1 else ""
                    code = lines[1] if len(lines) > 1 else part
                    if not code.strip():
                        code = part
                        lang = ""
                    widget.update_code(code, lang)
        else:
            # User bubble update
            if self.bubble_layout.count() > 0:
                self.bubble_layout.itemAt(0).widget().setText(text)
