from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QPlainTextEdit, QPushButton, QFrame)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor

class AgentDashboardPage(QWidget):
    """
    A UI page to monitor the Agentic AI Execution Engine and PoUW status.
    """
    
    # Signals that other parts of the app can use to update this UI
    log_received = Signal(str, str) # msg, level
    state_changed = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.setObjectName("AgentDashboardPage")
        self.init_ui()
        
        # Connect signals
        self.log_received.connect(self._append_log)
        self.state_changed.connect(self._update_state)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Header Title
        title = QLabel("Agentic Execution Engine")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #ffffff;")
        main_layout.addWidget(title)

        # Status Bar Frame
        status_frame = QFrame()
        status_frame.setObjectName("StatusFrame")
        status_frame.setStyleSheet("""
            QFrame#StatusFrame {
                background-color: #1e293b;
                border-radius: 10px;
                border: 1px solid #334155;
            }
        """)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(15, 10, 15, 10)

        # State Indicator
        state_label_title = QLabel("Current State:")
        state_label_title.setStyleSheet("color: #94a3b8; font-size: 14px;")
        
        self.state_indicator = QLabel("IDLE")
        self.state_indicator.setStyleSheet("""
            background-color: #334155;
            color: #cbd5e1;
            padding: 5px 12px;
            border-radius: 5px;
            font-weight: bold;
            font-size: 13px;
        """)
        
        status_layout.addWidget(state_label_title)
        status_layout.addWidget(self.state_indicator)
        status_layout.addStretch()

        # PoUW Placeholder
        mining_lbl = QLabel("PoUW Status: Inactive")
        mining_lbl.setStyleSheet("color: #64748b; font-size: 13px; font-style: italic;")
        status_layout.addWidget(mining_lbl)

        main_layout.addWidget(status_frame)

        # Console Logs Area
        log_label = QLabel("Execution Logs")
        log_label.setStyleSheet("color: #e2e8f0; font-size: 16px; font-weight: 600;")
        main_layout.addWidget(log_label)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0f172a;
                color: #a7f3d0;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
                border-radius: 10px;
                border: 1px solid #1e293b;
                padding: 10px;
            }
        """)
        main_layout.addWidget(self.console)
        
        # Initial Log
        self._append_log("Agentic Engine Initialized. Ready for tasks.", "INFO")

    @Slot(str, str)
    def _append_log(self, msg: str, level: str = "INFO"):
        cursor = self.console.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        fmt = QTextCharFormat()
        if level == "ERROR":
            fmt.setForeground(QColor("#f87171"))
        elif level == "WARNING":
            fmt.setForeground(QColor("#fbbf24"))
        elif level == "ACTION":
            fmt.setForeground(QColor("#60a5fa"))
        else:
            fmt.setForeground(QColor("#a7f3d0")) # Default greenish
            
        cursor.setCharFormat(fmt)
        cursor.insertText(f"> {msg}\n")
        self.console.setTextCursor(cursor)
        self.console.ensureCursorVisible()

    @Slot(str)
    def _update_state(self, state: str):
        color_map = {
            "IDLE": ("#cbd5e1", "#334155"),
            "THINKING": ("#ffffff", "#8b5cf6"),
            "ACTING": ("#ffffff", "#3b82f6"),
            "OBSERVING": ("#ffffff", "#10b981"),
            "COMPLETED": ("#ffffff", "#059669"),
            "ERROR": ("#ffffff", "#ef4444")
        }
        
        fg, bg = color_map.get(state, ("#cbd5e1", "#334155"))
        self.state_indicator.setText(state)
        self.state_indicator.setStyleSheet(f"""
            background-color: {bg};
            color: {fg};
            padding: 5px 12px;
            border-radius: 5px;
            font-weight: bold;
            font-size: 13px;
        """)
