import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QTextEdit, QLineEdit, QLabel, QSlider, QSpinBox, 
                               QDoubleSpinBox, QGroupBox, QMessageBox, QFileDialog,
                               QComboBox, QListWidget, QListWidgetItem, QSplitter,
                               QScrollArea, QFrame, QGridLayout)
from PySide6.QtCore import Qt, QTimer
import sqlite3
import json
from app.ui.chat_bubble import ChatBubbleWidget
from app.ui.toast import Toast
from ai.inference.local_llm_client import LocalLLMGenerator
from app.workers.inference_worker import InferenceWorker

class OverlayChatWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.input_container = None
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.input_container:
            h = self.input_container.sizeHint().height()
            self.input_container.setGeometry(0, self.height() - h, self.width(), h)

# NOTE: TextGenerator, transformers, and related HuggingFace imports are
# lazy-loaded inside _load_huggingface_model() to avoid a PySide6/shiboken
# conflict that crashes the app on startup.

# Model priority ranking — higher index = better quality.
# Used to auto-select the best available model on startup.
MODEL_PRIORITY = [
    # (display_name, ollama_tag, approx_size_gb)
    ("Llama 3.1 8B",           "llama3.1:8b",                    4.9),
    ("Mistral Small 3.1 24B",  "mistral-small3.1:24b",          14.0),
    ("Gemma 3 27B",            "gemma3:27b",                    16.0),
    ("Qwen 2.5 32B ⭐",        "qwen2.5:32b",                   19.0),
    ("DeepSeek-R1 32B",        "deepseek-r1:32b",               19.0),
    ("Mistral Small 32B",      "mistral-small:32b",             19.0),
    ("Mixtral 8x7B 47B",       "mixtral:8x7b",                  26.0),
    ("Qwen 2.5 72B",           "qwen2.5:72b",                   41.0),
    ("Llama 3.1 70B Q4_K_M",   "llama3.1:70b-instruct-q4_K_M", 41.5),
]

class ChatPage(QWidget):
    def __init__(self, db_manager=None):
        super().__init__()
        
        self.db_manager = db_manager
        self.tokenizer = None
        self.model = None
        self.generator = None
        self.worker = None
        self.voice_assistant = None
        self.voice_worker = None
        self.tts_worker = None
        self.current_session_id = None
        self._current_ai_response = ""
        
        self.init_ui()
        self._load_sessions_from_db()
        
        # Auto-detect and connect to the best available Ollama model on startup
        QTimer.singleShot(300, self._auto_detect_and_connect)
        QTimer.singleShot(500, self._silent_update_check)
        
    def init_ui(self):
        import os, sys
        from PySide6.QtGui import QIcon
        from PySide6.QtCore import QSize
        
        self.assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "assets", "icons")
            
        self.icon_speaker_on = QIcon(os.path.join(self.assets_dir, "speaker_on.png"))
        self.icon_speaker_off = QIcon(os.path.join(self.assets_dir, "speaker_off.png"))
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Use a QSplitter for resizable columns
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # --- LEFT: History Sidebar ---
        history_widget = QWidget()
        history_widget.setFixedWidth(240)
        history_layout = QVBoxLayout(history_widget)
        history_layout.setContentsMargins(0, 0, 10, 0)
        
        new_chat_btn = QPushButton("+ New Chat")
        new_chat_btn.setObjectName("NewChatBtn")
        new_chat_btn.clicked.connect(self.new_chat)
        history_layout.addWidget(new_chat_btn)
        
        self.history_list = QListWidget()
        self.history_list.setObjectName("HistoryList")
        self.history_list.itemClicked.connect(self._on_session_clicked)
        self.history_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self._show_history_context_menu)
        history_layout.addWidget(self.history_list)
        
        splitter.addWidget(history_widget)
        
        # --- CENTER: Chat Area ---
        # Main Chat Area (Right side)
        self.chat_widget = OverlayChatWidget()
        self.chat_widget.setObjectName("ChatArea")
        splitter.addWidget(self.chat_widget)
        chat_layout = QVBoxLayout(self.chat_widget)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        
        # Scroll Area for beautiful widgets
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.chat_scroll.viewport().setStyleSheet("background: transparent;")
        self.chat_scroll.verticalScrollBar().setStyleSheet("""
            QScrollBar:vertical { background: transparent; width: 6px; margin: 0px; }
            QScrollBar::handle:vertical { background: #334155; border-radius: 3px; }
            QScrollBar::handle:vertical:hover { background: #475569; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        
        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background-color: transparent;")
        self.chat_history_layout = QVBoxLayout(self.chat_container)
        self.chat_history_layout.setAlignment(Qt.AlignTop)
        # Extra bottom margin so text scrolls under the floating input box (approx 160px)
        self.chat_history_layout.setContentsMargins(10, 10, 10, 180)
        self.chat_history_layout.setSpacing(15)
        
        self.chat_scroll.setWidget(self.chat_container)
        chat_layout.addWidget(self.chat_scroll)
        
        # Rounded input frame like ChatGPT
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background-color: #212121;
                border-radius: 20px;
                border: 1px solid #2f2f2f;
            }
        """)
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(15, 10, 15, 10)
        
        # Top part of input frame: Model selector
        model_layout = QHBoxLayout()
        model_lbl = QLabel("Model:")
        model_lbl.setStyleSheet("color: #94a3b8; border: none; font-size: 12px; background: transparent;")
        
        self.ollama_model_combo = QComboBox()
        self.ollama_model_combo.addItem("Detecting models...")
        self.ollama_model_combo.setStyleSheet("""
            QComboBox {
                background-color: transparent;
                color: #38bdf8;
                border: none;
                font-weight: bold;
                font-size: 13px;
            }
            QComboBox::drop-down { border: none; }
        """)
        self.ollama_model_combo.currentIndexChanged.connect(self.load_model)
        
        model_layout.addWidget(model_lbl)
        model_layout.addWidget(self.ollama_model_combo)
        
        self.refresh_model_btn = QPushButton("🔄")
        self.refresh_model_btn.setStyleSheet("""
            QPushButton { background-color: transparent; border: none; font-size: 14px; }
            QPushButton:hover { background-color: #2f2f2f; border-radius: 4px; }
        """)
        self.refresh_model_btn.setFixedSize(24, 24)
        self.refresh_model_btn.setToolTip("Refresh Models")
        self.refresh_model_btn.clicked.connect(lambda: self._auto_detect_and_connect(quiet=True))
        model_layout.addWidget(self.refresh_model_btn)
        
        # Web Search Toggle
        from PySide6.QtWidgets import QCheckBox
        self.web_search_toggle = QCheckBox("🌐 Web Search")
        self.web_search_toggle.setStyleSheet("""
            QCheckBox {
                color: #a1a1aa;
                font-size: 13px;
                font-weight: bold;
                margin-left: 10px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid #3f3f46;
                background: #18181b;
            }
            QCheckBox::indicator:checked {
                background: #2563eb;
                border: 1px solid #2563eb;
            }
        """)
        model_layout.addWidget(self.web_search_toggle)
        
        # Vision Toggle
        self.vision_btn = QCheckBox("🖥️ Screen Vision")
        self.vision_btn.setStyleSheet("""
            QCheckBox {
                color: #a1a1aa;
                font-size: 13px;
                font-weight: bold;
                margin-left: 10px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid #3f3f46;
                background: #18181b;
            }
            QCheckBox::indicator:checked {
                background: #2563eb;
                border: 1px solid #2563eb;
            }
        """)
        model_layout.addWidget(self.vision_btn)

        # TTS Toggle
        self.tts_btn = QPushButton()
        self.tts_btn.setIcon(self.icon_speaker_off)
        self.tts_btn.setCheckable(True)
        self.tts_btn.setChecked(False)
        self.tts_btn.setToolTip("Auto Read Aloud (TTS)")
        self.tts_btn.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background: #334155; border-radius: 5px; }")
        self.tts_btn.toggled.connect(lambda checked: self.tts_btn.setIcon(self.icon_speaker_on if checked else self.icon_speaker_off))
        model_layout.addWidget(self.tts_btn)

        
        model_layout.addStretch()
        input_layout.addLayout(model_layout)
        
        # Attachment Pill Layout
        self.attachments_layout = QHBoxLayout()
        self.attachments_layout.setAlignment(Qt.AlignLeft)
        input_layout.addLayout(self.attachments_layout)
        
        self.attached_files = []
        
        # Bottom part of input frame: Attach button, Text input & Send button
        bottom_input_layout = QHBoxLayout()
        bottom_input_layout.setSpacing(6)
        bottom_input_layout.setContentsMargins(0, 0, 0, 0)
        
        self.attach_btn = QPushButton("+")
        self.attach_btn.setToolTip("Attach File")
        self.attach_btn.setFixedSize(32, 32)
        self.attach_btn.setCursor(Qt.PointingHandCursor)
        self.attach_btn.setStyleSheet("""
            QPushButton { 
                background-color: transparent; 
                border: none; 
                border-radius: 16px; 
                font-size: 20px; 
                color: #a3a3a3; 
                padding: 0px;
            }
            QPushButton:hover { 
                color: white; 
            }
        """)
        self.attach_btn.clicked.connect(self.on_attach_click)
        
        import os, sys
        from PySide6.QtGui import QIcon
        from PySide6.QtCore import QSize
        
        # Old assets dir reference removed
            
        self.icon_mic = QIcon(os.path.join(self.assets_dir, "mic.png"))
        self.icon_mic_rec = QIcon(os.path.join(self.assets_dir, "mic_recording.png"))
        self.icon_send = QIcon(os.path.join(self.assets_dir, "send.png"))
        self.icon_stop = QIcon(os.path.join(self.assets_dir, "stop.png"))
        
        self.mic_btn = QPushButton()
        self.mic_btn.setIcon(self.icon_mic)
        self.mic_btn.setIconSize(QSize(22, 22))
        self.mic_btn.setObjectName("MicBtn")
        self.mic_btn.setFixedSize(32, 32)
        self.mic_btn.setCursor(Qt.PointingHandCursor)
        self.mic_btn.setToolTip("Klik untuk merekam suara")
        self.mic_btn.setStyleSheet("""
            QPushButton { 
                background-color: transparent; 
                border: none; 
                border-radius: 16px; 
                padding: 0px;
            }
            QPushButton:hover { 
                background-color: #334155; 
            }
        """)
        self.mic_btn.clicked.connect(self.on_mic_clicked)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Message ZYRA...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: transparent;
                border: none;
                color: white;
                font-size: 14px;
            }
        """)
        self.input_field.returnPressed.connect(self.on_send_click)
        
        self.send_btn = QPushButton()
        self.send_btn.setIcon(self.icon_send)
        self.send_btn.setIconSize(QSize(20, 20))
        self.send_btn.setObjectName("SendBtn")
        self.send_btn.setFixedSize(36, 36)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #38bdf8;
                border-radius: 18px;
            }
            QPushButton:hover { background-color: #7dd3fc; }
            QPushButton:disabled { background-color: #475569; }
        """)
        self.send_btn.clicked.connect(self.on_send_click)
        
        bottom_input_layout.addWidget(self.attach_btn)
        bottom_input_layout.addWidget(self.mic_btn)
        bottom_input_layout.addWidget(self.input_field)
        bottom_input_layout.addWidget(self.send_btn)
        
        input_layout.addLayout(bottom_input_layout)
        
        # Overlay container for absolute positioning
        self.chat_widget.input_container = QWidget(self.chat_widget)
        self.chat_widget.input_container.setStyleSheet("background: transparent;")
        overlay_layout = QVBoxLayout(self.chat_widget.input_container)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        
        # Add a subtle gradient background to the overlay container to blend the bottom
        # Wait, using QFrame for the gradient makes it look incredibly premium
        gradient_frame = QFrame()
        gradient_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                            stop:0 transparent, stop:0.2 #171717, stop:1 #171717);
            }
        """)
        gradient_layout = QVBoxLayout(gradient_frame)
        gradient_layout.setContentsMargins(0, 20, 0, 0)
        
        input_wrapper = QHBoxLayout()
        input_wrapper.setContentsMargins(80, 10, 80, 10)
        input_wrapper.addWidget(input_frame)
        gradient_layout.addLayout(input_wrapper)
        
        # Metrics Status Bar
        metrics_layout = QHBoxLayout()
        self.latency_lbl = QLabel("Latency: 0 ms")
        self.tok_sec_lbl = QLabel("Tokens/sec: 0")
        self.vram_lbl = QLabel("VRAM: 0 MB")
        for lbl in (self.latency_lbl, self.tok_sec_lbl, self.vram_lbl):
            lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        metrics_layout.addWidget(self.latency_lbl)
        metrics_layout.addWidget(self.tok_sec_lbl)
        metrics_layout.addWidget(self.vram_lbl)
        metrics_layout.addStretch()
        
        gradient_layout.addLayout(metrics_layout)
        overlay_layout.addWidget(gradient_frame)
        
        # --- Settings Area (Exposed for SettingsPage) ---
        self.settings_widget = QWidget()
        settings_layout = QGridLayout(self.settings_widget)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setHorizontalSpacing(20)
        settings_layout.setVerticalSpacing(20)
        
        # --- Backend Selector ---
        backend_group = QGroupBox("Inference Backend")
        backend_layout = QVBoxLayout()
        
        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Local Ollama (Recommended)")
        self.backend_combo.addItem("HuggingFace (Legacy)")
        self.backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        backend_layout.addWidget(self.backend_combo)
        
        backend_group.setLayout(backend_layout)
        
        # --- Model Status ---
        load_group = QGroupBox("Model Status")
        load_layout = QVBoxLayout()
        self.status_lbl = QLabel("Status: No Model Loaded")
        self.load_btn = QPushButton("Connect / Load Model")
        self.load_btn.clicked.connect(self.load_model)
        load_layout.addWidget(self.status_lbl)
        load_layout.addWidget(self.load_btn)
        load_group.setLayout(load_layout)
        
        param_group = QGroupBox("Generation Parameters")
        param_layout = QVBoxLayout()
        
        param_layout.addWidget(QLabel("Temperature"))
        self.temp_input = QDoubleSpinBox()
        self.temp_input.setRange(0.0, 2.0)
        self.temp_input.setSingleStep(0.1)
        self.temp_input.setValue(0.7)
        param_layout.addWidget(self.temp_input)
        
        param_layout.addWidget(QLabel("Top-K"))
        self.topk_input = QSpinBox()
        self.topk_input.setRange(0, 100)
        self.topk_input.setValue(40)
        param_layout.addWidget(self.topk_input)
        
        param_layout.addWidget(QLabel("Top-P"))
        self.topp_input = QDoubleSpinBox()
        self.topp_input.setRange(0.0, 1.0)
        self.topp_input.setSingleStep(0.05)
        self.topp_input.setValue(0.9)
        param_layout.addWidget(self.topp_input)
        
        param_layout.addWidget(QLabel("Max Tokens"))
        self.max_tokens_input = QSpinBox()
        self.max_tokens_input.setRange(1, 8192)
        self.max_tokens_input.setValue(4096)
        param_layout.addWidget(self.max_tokens_input)
        
        param_group.setLayout(param_layout)
        
        # System Prompt Group
        prompt_group = QGroupBox("System Prompt")
        prompt_layout = QVBoxLayout()
        from PySide6.QtWidgets import QTextEdit
        from PySide6.QtCore import QSettings
        
        self.settings = QSettings("ZYRA", "ZYRA_AI")
        default_prompt = ("Kamu adalah asisten AI lokal yang cerdas, ramah, dan membantu. "
                          "Selalu balas menggunakan bahasa yang sama dengan pengguna. "
                          "Jika pengguna berbicara bahasa Indonesia, balas dalam bahasa Indonesia. "
                          "Jika pengguna berbicara bahasa Inggris, balas dalam bahasa Inggris. "
                          "Berikan jawaban yang jelas, ringkas, dan informatif.")
        saved_prompt = self.settings.value("system_prompt", default_prompt)
        
        self.system_prompt_input = QTextEdit()
        self.system_prompt_input.setText(saved_prompt)
        self.system_prompt_input.setMaximumHeight(100)
        
        def save_prompt():
            self.settings.setValue("system_prompt", self.system_prompt_input.toPlainText().strip())
            Toast(self, "System Prompt Saved!").show()
            
        self.save_prompt_btn = QPushButton("Save Prompt")
        self.save_prompt_btn.clicked.connect(save_prompt)
        self.save_prompt_btn.setCursor(Qt.PointingHandCursor)
        
        prompt_layout.addWidget(self.system_prompt_input)
        prompt_layout.addWidget(self.save_prompt_btn)
        prompt_group.setLayout(prompt_layout)
        
        # System Update Group
        update_group = QGroupBox("System Update")
        update_layout = QVBoxLayout()
        self.update_status_lbl = QLabel("App is up to date.")
        self.update_status_lbl.setWordWrap(True)
        self.check_update_btn = QPushButton("Check for Updates")
        self.check_update_btn.setCursor(Qt.PointingHandCursor)
        self.check_update_btn.clicked.connect(self.check_for_updates)
        
        from PySide6.QtWidgets import QProgressBar
        self.update_progress = QProgressBar()
        self.update_progress.setVisible(False)
        
        update_layout.addWidget(self.update_status_lbl)
        update_layout.addWidget(self.update_progress)
        update_layout.addWidget(self.check_update_btn)
        update_group.setLayout(update_layout)
        
        # Left Column
        settings_layout.addWidget(backend_group, 0, 0)
        settings_layout.addWidget(load_group, 1, 0)
        settings_layout.addWidget(param_group, 2, 0)
        
        # Right Column
        settings_layout.addWidget(prompt_group, 0, 1, 2, 1) # spans row 0 and 1
        settings_layout.addWidget(update_group, 2, 1, Qt.AlignTop)
        
        settings_layout.setRowStretch(3, 1) # Push everything up
        
        # Adjust initial splitter sizes
        splitter.setSizes([240, 800])
        
        # Trigger initial visibility
        self._on_backend_changed(0)
        self.new_chat() # Init empty chat

    def on_send_click(self):
        if self.worker and self.worker.isRunning():
            self.stop_generation()
        else:
            self.start_generation()

    def _clear_chat_layout(self):
        while self.chat_history_layout.count():
            child = self.chat_history_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def new_chat(self):
        """Starts a new chat session."""
        self.current_session_id = None
        self._clear_chat_layout()
        self.history_list.clearSelection()
        
        # Disable sending/stopping if an AI is already generating somewhere else
        if self.worker and self.worker.isRunning():
            self.send_btn.setEnabled(False)
        else:
            self.send_btn.setEnabled(True)
            self.send_btn.setIcon(self.icon_send)
            self.send_btn.setStyleSheet("""
                QPushButton {
                    background-color: #38bdf8;
                    color: #0f172a;
                    border-radius: 12px;
                    padding: 8px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #7dd3fc; }
                QPushButton:disabled { background-color: #475569; color: #94a3b8; }
            """)
        
        # Show welcome message
        welcome = QLabel(
            "<div style='text-align: center; color: #64748b; margin-top: 100px;'>"
            "<h2 style='color: #38bdf8; font-size: 32px; font-weight: bold;'>ZYRA</h2>"
            "<p style='font-size: 16px;'>Lokal, Privat, dan Aman 🚀</p>"
            "</div>"
        )
        welcome.setAlignment(Qt.AlignCenter)
        self.chat_history_layout.addWidget(welcome)

    def _load_sessions_from_db(self):
        """Load history sidebar items from database."""
        if not self.db_manager or not self.db_manager.connection:
            return
            
        self.history_list.clear()
        cursor = self.db_manager.connection.cursor()
        cursor.execute("SELECT id, title, model_name FROM chat_sessions ORDER BY updated_at DESC")
        
        for session_id, title, model_name in cursor.fetchall():
            item = QListWidgetItem(f"💬 {title}")
            item.setData(Qt.UserRole, session_id)
            self.history_list.addItem(item)

    def show_toast(self, message, type="info", duration=5000):
        # We pass self.parent() or self as parent. 
        # Using self (ChatPage) makes it float over the ChatPage area.
        toast = Toast(self, message, duration, type)
        toast.show_toast()

    def _show_history_context_menu(self, pos):
        item = self.history_list.itemAt(pos)
        if not item:
            return
            
        from PySide6.QtWidgets import QMenu, QInputDialog, QMessageBox
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #212121; color: white; border: 1px solid #2f2f2f; border-radius: 8px; }
            QMenu::item { padding: 8px 24px; }
            QMenu::item:selected { background-color: #3b82f6; }
        """)
        rename_action = menu.addAction("✏️ Rename")
        delete_action = menu.addAction("🗑️ Delete")
        
        action = menu.exec_(self.history_list.mapToGlobal(pos))
        
        if action == rename_action:
            session_id = item.data(Qt.UserRole)
            current_title = item.text().replace("💬 ", "")
            new_title, ok = QInputDialog.getText(self, "Rename Chat", "New name:", text=current_title)
            if ok and new_title.strip():
                if self.db_manager and self.db_manager.connection:
                    cursor = self.db_manager.connection.cursor()
                    cursor.execute("UPDATE chat_sessions SET title=? WHERE id=?", (new_title.strip(), session_id))
                    self.db_manager.connection.commit()
                    self._load_sessions_from_db()
                    
        elif action == delete_action:
            session_id = item.data(Qt.UserRole)
            reply = QMessageBox.question(self, "Delete Chat", "Are you sure you want to delete this chat?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                if self.db_manager and self.db_manager.connection:
                    cursor = self.db_manager.connection.cursor()
                    cursor.execute("DELETE FROM chat_messages WHERE session_id=?", (session_id,))
                    cursor.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))
                    self.db_manager.connection.commit()
                    self._load_sessions_from_db()
                    if self.current_session_id == session_id:
                        self.new_chat()

    def _scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum()))

    def _on_session_clicked(self, item: QListWidgetItem):
        """Load chat messages when a session is clicked."""
        if not self.db_manager or not self.db_manager.connection:
            return
            
        session_id = item.data(Qt.UserRole)
        self.current_session_id = session_id
        self._clear_chat_layout()
        
        cursor = self.db_manager.connection.cursor()
        cursor.execute("SELECT role, content FROM chat_messages WHERE session_id=? ORDER BY created_at ASC", (session_id,))
        
        for role, content in cursor.fetchall():
            bubble = ChatBubbleWidget(role, content)
            self.chat_history_layout.addWidget(bubble)
                
        # If the user clicked back to the session that is currently generating
        active_gen_id = getattr(self, '_active_generation_session_id', None)
        if self.worker and self.worker.isRunning():
            if session_id == active_gen_id:
                self.send_btn.setEnabled(True)
                self.send_btn.setIcon(self.icon_stop)
                self.send_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #ef4444; color: white; border-radius: 12px; padding: 8px; font-weight: bold;
                    }
                    QPushButton:hover { background-color: #f87171; }
                """)
                # We need to show the text that has been generating so far
                self._current_ai_bubble = ChatBubbleWidget("ai", getattr(self, '_current_ai_response', ''))
                self.chat_history_layout.addWidget(self._current_ai_bubble)
            else:
                self.send_btn.setEnabled(False)
        else:
            self.send_btn.setEnabled(True)
            self.send_btn.setIcon(self.icon_send)
            self.send_btn.setStyleSheet("""
                QPushButton {
                    background-color: #38bdf8;
                    color: #0f172a;
                    border-radius: 12px;
                    padding: 8px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #7dd3fc; }
                QPushButton:disabled { background-color: #475569; color: #94a3b8; }
            """)
        
        self._scroll_to_bottom()

    def _on_backend_changed(self, index: int):
        """Show/hide Ollama model selector based on selected backend."""
        is_ollama = (index == 0)
        self.ollama_model_combo.setVisible(is_ollama)
        # Reset generator when switching backends
        self.generator = None
        self.status_lbl.setText("Status: No Model Loaded")

    def _auto_detect_and_connect(self, quiet=False):
        """Query Ollama for installed models, populate dropdown, auto-connect to the best one."""
        import httpx
        import threading
        from PySide6.QtCore import QObject, Signal
        
        class WorkerSignals(QObject):
            bad_status = Signal()
            no_models = Signal()
            success = Signal(list)
            error = Signal()
            
        self._detect_signals = WorkerSignals()
        signals = self._detect_signals
        
        def on_bad_status():
            self.status_lbl.setText("Status: Ollama not responding")
            self.ollama_model_combo.setItemText(0, "Ollama not responding")
            
        def on_no_models():
            self.status_lbl.setText("Status: No Ollama models found")
            self.ollama_model_combo.setItemText(0, "No models found")
            self.show_toast("No models installed in Ollama. Pull a model first: ollama pull qwen2.5:32b", type="warning", duration=8000)
            
        def on_success(matched):
            self.ollama_model_combo.currentIndexChanged.disconnect(self.load_model)
            self.ollama_model_combo.clear()
            for display_name, tag, size in matched:
                self.ollama_model_combo.addItem(f"{display_name}", userData=tag)
            self.ollama_model_combo.currentIndexChanged.connect(self.load_model)
            
            best_name, best_tag, best_size = matched[0]
            if not quiet:
                self.show_toast(f"Auto-detected {len(matched)} installed model(s). Best available: {best_name} ({best_size:.0f} GB)", type="info")
                
            self._load_ollama_model(quiet=quiet)
            
        def on_error():
            if not quiet:
                self.status_lbl.setText("Status: Ollama offline. Retrying...")
                self.ollama_model_combo.setItemText(0, "Ollama offline...")
                if not hasattr(self, '_ollama_offline_warned'):
                    self.show_toast("Could not reach Ollama engine. Auto-retrying in the background...", type="warning")
                    self._ollama_offline_warned = True
                QTimer.singleShot(5000, lambda: self._auto_detect_and_connect(quiet))
                
        signals.bad_status.connect(on_bad_status)
        signals.no_models.connect(on_no_models)
        signals.success.connect(on_success)
        signals.error.connect(on_error)
        
        if not quiet:
            self.status_lbl.setText("Status: Auto-detecting models...")
        self.repaint()
        
        def worker():
            try:
                resp = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
                if resp.status_code != 200:
                    if not quiet: signals.bad_status.emit()
                    return
                
                data = resp.json()
                installed_tags = {m["name"] for m in data.get("models", [])}
                
                matched = []
                for display_name, tag, size_gb in MODEL_PRIORITY:
                    tag_variants = [tag, tag + ":latest", tag.split(":")[0] + ":latest"]
                    if any(t in installed_tags for t in tag_variants):
                        matched.append((display_name, tag, size_gb))
                
                known_tags = {tag for _, tag, _ in MODEL_PRIORITY}
                for installed_tag in installed_tags:
                    base = installed_tag.replace(":latest", "")
                    if base not in known_tags and installed_tag not in known_tags:
                        matched.append((installed_tag, base, 0))
                
                if not matched:
                    if not quiet: signals.no_models.emit()
                    return
                
                matched.sort(key=lambda x: x[2], reverse=True)
                signals.success.emit(matched)
                
            except Exception as e:
                signals.error.emit()
                
        threading.Thread(target=worker, daemon=True).start()

    def load_model(self):
        """Loads model from the selected backend."""
        backend_index = self.backend_combo.currentIndex()
        
        if backend_index == 0:
            self._load_ollama_model()
        else:
            self._load_huggingface_model()

    def _load_ollama_model(self, quiet=False):
        """Connect to the local Ollama engine with the selected model."""
        try:
            if not quiet:
                self.status_lbl.setText("Status: Connecting to Ollama...")
            self.load_btn.setEnabled(False)
            self.repaint()
            
            display_name = self.ollama_model_combo.currentText()
            # Retrieve stored tag from combo item data, fallback to text
            model_tag = self.ollama_model_combo.currentData() or display_name
            
            self.generator = LocalLLMGenerator(
                base_url="http://localhost:11434/v1",
                model_name=model_tag
            )
            
            # Quick health check — try to reach the Ollama server
            import httpx
            import threading
            from PySide6.QtCore import QObject, Signal
            
            class HealthSignals(QObject):
                success = Signal()
                fail = Signal()
                always = Signal()
                
            self._health_signals = HealthSignals()
            signals = self._health_signals
            
            def on_success():
                self.status_lbl.setText(f"Status: Connected — {display_name}")
                self.show_toast(f"Connected to local Ollama engine. Model: {model_tag}. Ready to generate.", type="success")
                
            def on_fail():
                self.status_lbl.setText(f"Status: Ollama offline — will retry on send")
                self.show_toast(f"Warning: Ollama offline at localhost. Model set to {model_tag}. Will auto-retry on send.", type="warning", duration=8000)
                
            signals.success.connect(on_success)
            signals.fail.connect(on_fail)
            signals.always.connect(lambda: self.load_btn.setEnabled(True))
            
            def check_health():
                try:
                    resp = httpx.get("http://localhost:11434", timeout=3.0)
                    if resp.status_code == 200:
                        if not quiet: signals.success.emit()
                    else:
                        raise ConnectionError(f"Ollama returned status {resp.status_code}")
                except Exception:
                    if not quiet: signals.fail.emit()
                finally:
                    signals.always.emit()
            
            threading.Thread(target=check_health, daemon=True).start()
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            if not quiet:
                self.status_lbl.setText("Status: Error")
            self.load_btn.setEnabled(True)
            if not quiet:
                QMessageBox.critical(self, "Connection Error", str(e))

    def _load_huggingface_model(self):
        """Loads the HuggingFace model (legacy path)."""
        try:
            self.status_lbl.setText("Status: Loading HuggingFace model...")
            self.load_btn.setEnabled(False)
            self.repaint() # Force UI update before blocking
            
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from ai.inference.generator import TextGenerator
            import torch
            
            model_id = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
            
            self.tokenizer = AutoTokenizer.from_pretrained(model_id)
            self.model = AutoModelForCausalLM.from_pretrained(
                model_id,
                device_map="auto" if self.device.type == "cuda" else None,
                torch_dtype=torch.float32 if self.device.type == "cpu" else torch.float16
            )
            if self.device.type == "cpu":
                self.model.to("cpu")
            self.model.eval()
            
            self.generator = TextGenerator(self.model, self.tokenizer, self.device)
            
            self.status_lbl.setText(f"Status: Loaded TinyLlama")
            self.load_btn.setEnabled(True)
            msg = f"<i>Loaded HuggingFace model: {model_id}. Ready to generate.</i>"
            self.chat_history_layout.addWidget(ChatBubbleWidget("ai", msg))
            self._scroll_to_bottom()
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status_lbl.setText("Status: Error")
            self.load_btn.setEnabled(True)
            QMessageBox.critical(self, "Load Error", str(e))

    def on_attach_click(self):
        from PySide6.QtWidgets import QFileDialog
        files, _ = QFileDialog.getOpenFileNames(
            self, "Attach Files", "", 
            "All Supported (*.txt *.md *.csv *.json *.py *.js *.html *.css *.pdf *.docx *.png *.jpg *.jpeg);;Text Files (*.txt *.md *.csv *.json *.py *.js *.html *.css);;PDF & Docs (*.pdf *.docx);;Images (*.png *.jpg *.jpeg);;All Files (*)"
        )
        
        for file_path in files:
            if file_path not in self.attached_files:
                self.attached_files.append(file_path)
                self._add_attachment_pill(file_path)

    def _add_attachment_pill(self, file_path):
        import os
        filename = os.path.basename(file_path)
        
        pill = QWidget()
        pill.setStyleSheet("""
            QWidget { background-color: #2f2f2f; border-radius: 12px; border: 1px solid #3f3f3f; }
            QLabel { background: transparent; color: #f8fafc; font-size: 12px; border: none; }
            QPushButton { background: transparent; color: #ef4444; font-weight: bold; font-size: 12px; border: none; border-radius: 8px; }
            QPushButton:hover { background-color: #ef4444; color: white; }
        """)
        
        layout = QHBoxLayout(pill)
        layout.setContentsMargins(10, 4, 4, 4)
        layout.setSpacing(5)
        
        lbl = QLabel(f"📄 {filename}")
        layout.addWidget(lbl)
        
        rm_btn = QPushButton("✕")
        rm_btn.setFixedSize(20, 20)
        rm_btn.setCursor(Qt.PointingHandCursor)
        rm_btn.setStyleSheet("""
            QPushButton {
                background: transparent; 
                color: #ef4444; 
                font-weight: bold; 
                font-size: 14px;
                border: none;
            }
            QPushButton:hover {
                color: #f87171;
            }
        """)
        rm_btn.clicked.connect(lambda: self.remove_attachment(file_path, pill))
        layout.addWidget(rm_btn)
        
        self.attachments_layout.addWidget(pill)
        
        # Force overlay resize to prevent squishing
        if hasattr(self, 'chat_widget') and hasattr(self.chat_widget, 'resizeEvent'):
            from PySide6.QtGui import QResizeEvent
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            self.chat_widget.input_container.adjustSize()
            self.chat_widget.resizeEvent(QResizeEvent(self.chat_widget.size(), self.chat_widget.size()))

    def remove_attachment(self, file_path, pill_widget):
        if file_path in self.attached_files:
            self.attached_files.remove(file_path)
        pill_widget.setParent(None)
        pill_widget.deleteLater()
        
        # Force overlay resize to prevent squishing
        if hasattr(self, 'chat_widget') and hasattr(self.chat_widget, 'resizeEvent'):
            from PySide6.QtGui import QResizeEvent
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            self.chat_widget.input_container.adjustSize()
            self.chat_widget.resizeEvent(QResizeEvent(self.chat_widget.size(), self.chat_widget.size()))

    def _extract_file_content(self, file_path) -> str:
        import os
        import sys
        
        # Add bundled libs to path
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        libs_dir = os.path.join(base_dir, "libs")
        if libs_dir not in sys.path:
            sys.path.insert(0, libs_dir)
            
        ext = os.path.splitext(file_path)[1].lower()
        
        # Images will be handled by base64 encoder if backend supports it.
        # But for text extraction context, we just return a placeholder or nothing for images
        if ext in ['.png', '.jpg', '.jpeg']:
            return f"[Image attached: {os.path.basename(file_path)}]"
            
        try:
            if ext == '.pdf':
                try:
                    import PyPDF2
                    text = ""
                    with open(file_path, 'rb') as f:
                        reader = PyPDF2.PdfReader(f)
                        for page in reader.pages:
                            text += page.extract_text() + "\n"
                    return text
                except ImportError:
                    return f"[Error: PyPDF2 library not installed. Cannot read {os.path.basename(file_path)}]"
            elif ext == '.docx':
                try:
                    import docx
                    doc = docx.Document(file_path)
                    return "\n".join([p.text for p in doc.paragraphs])
                except ImportError:
                    return f"[Error: python-docx library not installed. Cannot read {os.path.basename(file_path)}]"
            else:
                # Default to text
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception as e:
            return f"[Error reading file {os.path.basename(file_path)}: {str(e)}]"

    def on_send_click(self):
        prompt = self.input_field.text().strip()
        
        if not prompt and not self.attached_files and not self.vision_btn.isChecked():
            return
            
        if self.worker and self.worker.isRunning():
            # Stop generation
            self.worker.stop()
            self.send_btn.setEnabled(False)
            self.send_btn.setIcon(self.icon_stop)
            return

        display_prompt = prompt
        
        # Prepare context from attachments
        attachment_context = ""
        has_images = False
        image_paths = []
        
        # Screen Context Capture
        if self.vision_btn.isChecked():
            import time
            try:
                from PIL import ImageGrab
                import tempfile
                import os
                screenshot = ImageGrab.grab()
                
                # Resize if it's too large to save inference time (max 1920x1080)
                screenshot.thumbnail((1920, 1080))
                
                # Save to temp
                temp_dir = tempfile.gettempdir()
                vision_path = os.path.join(temp_dir, f"zyra_vision_{int(time.time())}.jpg")
                screenshot.save(vision_path, format="JPEG", quality=85)
                
                image_paths.append(vision_path)
                has_images = True
                
                if display_prompt:
                    display_prompt += "\n\n[Attached: Screen Context]"
                else:
                    display_prompt = "[Attached: Screen Context]"
                    prompt = "Tolong jelaskan apa yang ada di layar saya." # Default prompt
                    
                self.vision_btn.setChecked(False) # Auto turn off after capturing
            except Exception as e:
                self.logger.error(f"Failed to capture screen: {e}")
        
        if self.attached_files:
            import os
            file_names = [os.path.basename(f) for f in self.attached_files]
            if display_prompt:
                display_prompt += "\n\n"
            for f_name in file_names:
                display_prompt += f"📎 {f_name}\n"
            display_prompt = display_prompt.strip()
            
            document_paths = []
            for fp in self.attached_files:
                ext = os.path.splitext(fp)[1].lower()
                if ext in ['.png', '.jpg', '.jpeg']:
                    has_images = True
                    image_paths.append(fp)
                else:
                    document_paths.append(fp)
                    
            if document_paths:
                from app.core.rag import retrieve_relevant_context
                from PySide6.QtWidgets import QApplication
                
                def update_progress(msg):
                    self.show_toast(msg, type="info", duration=1500)
                    QApplication.processEvents()
                    
                model_name = self.ollama_model_combo.currentData()
                if not model_name:
                    model_name = "llama3.2:1b" # fallback
                    
                try:
                    attachment_context = retrieve_relevant_context(
                        query=prompt,
                        file_paths=document_paths,
                        model_name=model_name,
                        top_k=3,
                        progress_callback=update_progress
                    )
                except Exception as e:
                    self.logger.error(f"RAG Error: {e}")
                    self.show_toast(f"RAG Error: {e}", type="error", duration=3000)


            # Clear attachments after sending
            self.attached_files.clear()
            while self.attachments_layout.count():
                item = self.attachments_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            # Force overlay resize to prevent squishing
            if hasattr(self, 'chat_widget') and hasattr(self.chat_widget, 'resizeEvent'):
                from PySide6.QtGui import QResizeEvent
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
                self.chat_widget.input_container.adjustSize()
                self.chat_widget.resizeEvent(QResizeEvent(self.chat_widget.size(), self.chat_widget.size()))
                    
        # Append context to prompt implicitly (user doesn't see the huge text in bubble)
        full_prompt = display_prompt + attachment_context
        
        # Add Web Search Context if toggled
        if hasattr(self, 'web_search_toggle') and self.web_search_toggle.isChecked():
            from app.utils.web_search import search_web
            self.show_toast("Searching the web...", type="info", duration=2000)
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents() # Force UI update to show toast
            
            web_context = search_web(prompt, max_results=3)
            full_prompt += f"\n\n--- WEB SEARCH RESULTS ---\n{web_context}\n--------------------------\nPlease answer the user's question using the context above if it is relevant."
            
        if not self.generator:
            QMessageBox.warning(self, "No Backend", "Please connect to an AI model first.")
            return
            
        # 1. Database - Create session if none
        if self.db_manager and self.db_manager.connection and not self.current_session_id:
            title = display_prompt[:30] + "..." if len(display_prompt) > 30 else (display_prompt if display_prompt else "File Analysis")
            model_tag = self.ollama_model_combo.currentData() or self.ollama_model_combo.currentText()
            cursor = self.db_manager.connection.cursor()
            cursor.execute("INSERT INTO chat_sessions (title, model_name) VALUES (?, ?)", (title, model_tag))
            self.current_session_id = cursor.lastrowid
            self.db_manager.connection.commit()
            self._load_sessions_from_db() # Refresh sidebar
            
        # 2. Database - Save user message
        if self.db_manager and self.db_manager.connection and self.current_session_id:
            cursor = self.db_manager.connection.cursor()
            cursor.execute("INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)", 
                           (self.current_session_id, "user", display_prompt))
            cursor.execute("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (self.current_session_id,))
            self.db_manager.connection.commit()
            
        # Append user prompt with right-aligned bubble
        user_bubble = ChatBubbleWidget("user", display_prompt)
        self.chat_history_layout.addWidget(user_bubble)
        self._scroll_to_bottom()
        
        self.input_field.clear()
        
        # Lock the current generation to this session
        self._active_generation_session_id = self.current_session_id
        
        # Fetch history from DB for context awareness
        history_msgs = []
        if self.db_manager and self.db_manager.connection:
            cursor = self.db_manager.connection.cursor()
            cursor.execute("SELECT role, content FROM chat_messages WHERE session_id=? ORDER BY created_at ASC", (self.current_session_id,))
            for r, c in cursor.fetchall():
                # Map 'ai' role back to 'assistant' for OpenAI API compatibility
                api_role = "assistant" if r == "ai" else r
                history_msgs.append({"role": api_role, "content": c})
            # Remove the last user message because we pass it as 'prompt'
            if history_msgs and history_msgs[-1]["role"] == "user":
                history_msgs.pop()
        
        
        self.send_btn.setIcon(self.icon_stop)
        self.send_btn.setStyleSheet("background-color: #ef4444; border: 1px solid #dc2626;")
        
        # Reset generation state
        self._first_token_received = False
        self._current_ai_response = ""
        self._thinking_phase = 0
        
        # UI Pre-setup for typing
        self._current_ai_bubble = ChatBubbleWidget("ai", "●○○")
        self.chat_history_layout.addWidget(self._current_ai_bubble)
        self._scroll_to_bottom()
        
        # Create a timer to animate the loading dots
        self.loading_state = 0
        self.loading_timer = QTimer(self)
        self.loading_timer.timeout.connect(self._animate_loading)
        self.loading_timer.start(150)
        
        self.worker = InferenceWorker(
            generator=self.generator,
            prompt=full_prompt,
            image_paths=image_paths,
            history=history_msgs,
            max_tokens=self.max_tokens_input.value(),
            temperature=self.temp_input.value(),
            top_k=self.topk_input.value(),
            top_p=self.topp_input.value()
        )
        
        self.worker.token_generated.connect(self.on_token_generated)
        self.worker.metrics_updated.connect(self.on_metrics_updated)
        self.worker.generation_finished.connect(self.on_generation_finished)
        self.worker.generation_error.connect(self.on_generation_error)
        self.worker.security_check_requested.connect(self.handle_security_check)
        
        self.worker.start()

    def _animate_loading(self):
        if not self._first_token_received:
            states = ["●○○", "○●○", "○○●"]
            self.loading_state = (self.loading_state + 1) % 3
            if hasattr(self, '_current_ai_bubble'):
                self._current_ai_bubble.update_content(states[self.loading_state])

    def on_token_generated(self, full_text: str, delta: str):
        from PySide6.QtGui import QTextCursor
        
        # Only render to the screen if the user is currently looking at the session that is generating
        if self.current_session_id != getattr(self, '_active_generation_session_id', None):
            self._current_ai_response = full_text
            return
            
        if not self._first_token_received:
            self._first_token_received = True
            if hasattr(self, 'loading_timer'):
                self.loading_timer.stop()
            
        self._current_ai_response = full_text
        
        # Smooth streaming by updating widget content directly
        if hasattr(self, '_current_ai_bubble'):
            self._current_ai_bubble.update_content(full_text)
        
        self._scroll_to_bottom()

    def stop_generation(self):
        if self.worker:
            self.worker.stop()

    def on_metrics_updated(self, latency: float, tok_sec: float, vram: float):
        self.latency_lbl.setText(f"Latency: {latency:.1f} ms")
        self.tok_sec_lbl.setText(f"Tokens/sec: {tok_sec:.1f}")
        self.vram_lbl.setText(f"VRAM: {vram:.1f} MB")

    def on_generation_finished(self):
        active_session = getattr(self, '_active_generation_session_id', None)
            
        # Save AI response to DB
        if hasattr(self, '_current_ai_response') and self.db_manager and self.db_manager.connection and active_session:
            cursor = self.db_manager.connection.cursor()
            cursor.execute("INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)", 
                           (active_session, "ai", getattr(self, '_current_ai_response')))
            self.db_manager.connection.commit()
            
        self.send_btn.setEnabled(True)
        self.send_btn.setIcon(self.icon_send)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #38bdf8;
                color: #0f172a;
                border-radius: 12px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #7dd3fc; }
            QPushButton:disabled { background-color: #475569; color: #94a3b8; }
        """)
        if hasattr(self, 'loading_timer'):
            self.loading_timer.stop()
        self._active_generation_session_id = None

        # Trigger TTS if enabled
        if self.tts_btn.isChecked() and self._current_ai_response.strip():
            try:
                from app.workers.tts_worker import TTSWorker
                if self.tts_worker and self.tts_worker.isRunning():
                    self.tts_worker.stop()
                    self.tts_worker.wait()
                self.tts_worker = TTSWorker(self._current_ai_response, parent=self)
                self.tts_worker.start()
            except ImportError:
                print("TTS Disabled: edge-tts is not installed in this environment.")
            except Exception as e:
                print(f"TTS Error: {e}")


    def _parse_version(self, v):
        try:
            return tuple(map(int, str(v).replace('v', '').split('.')))
        except:
            return (0, 0, 0)

    def check_for_updates(self):
        import json, requests
        self.check_update_btn.setText("Checking...")
        self.check_update_btn.setEnabled(False)
        self.repaint()
        
        try:
            import time
            resp = requests.get(f"https://raw.githubusercontent.com/annabil-dev/ZYRA/main/publish/version.json?t={int(time.time())}", timeout=5)
            if resp.status_code == 200:
                v_info = resp.json()
            else:
                raise Exception(f"HTTP {resp.status_code}")
        except Exception as e:
            QMessageBox.warning(self, "Updater", f"Failed to check for updates: {e}")
            self.check_update_btn.setText("Check for Updates")
            self.check_update_btn.setEnabled(True)
            return

        import os, sys
        user_data_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ZYRA AI")
            
        current_version = "v1.0.81" # The base bundled version
        current_v_path = os.path.join(user_data_dir, "current_version.json")
        if os.path.exists(current_v_path):
            try:
                with open(current_v_path, 'r') as f:
                    current_version = json.load(f).get("version", "v1.0.81")
            except Exception:
                pass
                
        pub_version = v_info.get("version", "v1.0.81")
        
        self.check_update_btn.setText("Check for Updates")
        self.check_update_btn.setEnabled(True)
        
        if self._parse_version(pub_version) <= self._parse_version(current_version):
            QMessageBox.information(self, "Updater", f"You are already on the latest version ({current_version}).")
            return
            
        reply = QMessageBox.question(self, "Update Available", 
                                     f"New OTA Update found!\nDesc: {v_info.get('description')}\nNew Version: {pub_version}\nCurrent Version: {current_version}\n\nUpdate now?",
                                     QMessageBox.Yes | QMessageBox.No)
                                     
        if reply == QMessageBox.Yes:
            self._apply_update(v_info)
            
    def _apply_update(self, v_info):
        import os, sys, time, zipfile, json, requests, io, shutil
        import threading
        from PySide6.QtCore import QObject, Signal
        
        self.update_progress.setVisible(True)
        self.update_progress.setRange(0, 0) # indeterminate
        self.update_status_lbl.setText("Downloading from GitHub...")
        self.check_update_btn.setEnabled(False)
        self.repaint()
        
        class UpdateTaskSignals(QObject):
            progress = Signal(str, int)
            finished = Signal()
            error = Signal(str)
            
        self._update_task_signals = UpdateTaskSignals()
        signals = self._update_task_signals
        
        def on_progress(text, pct):
            self.update_status_lbl.setText(text)
            if pct >= 0:
                self.update_progress.setRange(0, 100)
                self.update_progress.setValue(pct)
            else:
                self.update_progress.setRange(0, 0)
                
        def on_finished():
            self.update_status_lbl.setText("Update complete. Restarting...")
            self.update_progress.setRange(0, 100)
            self.update_progress.setValue(100)
            
            # Restart
            import subprocess
            from PySide6.QtWidgets import QApplication
            exe_path = sys.executable
            if getattr(sys, 'frozen', False):
                subprocess.Popen([exe_path])
            else:
                run_script = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "run.py")
                subprocess.Popen([exe_path, run_script])
            QApplication.instance().quit()
                
        def on_error(err_msg):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Update Failed", f"Failed to download/apply update:\n{err_msg}")
            self.update_status_lbl.setText("Update failed.")
            self.update_progress.setVisible(False)
            self.check_update_btn.setEnabled(True)
            
        signals.progress.connect(on_progress)
        signals.finished.connect(on_finished)
        signals.error.connect(on_error)
        
        def worker():
            try:
                import time
                # Use a cache-busting query parameter
                url = f"https://github.com/annabil-dev/ZYRA/archive/refs/heads/main.zip?t={int(time.time())}"
                headers = {'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}
                resp = requests.get(url, stream=True, timeout=30, headers=headers)
                resp.raise_for_status()
                
                total_size = int(resp.headers.get('content-length', 0))
                downloaded = 0
                zip_data = io.BytesIO()
                
                for chunk in resp.iter_content(chunk_size=16384):
                    if chunk:
                        zip_data.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = int((downloaded / total_size) * 50)
                            signals.progress.emit(f"Downloading... {downloaded//1024} KB", pct)
                        else:
                            signals.progress.emit(f"Downloading... {downloaded//1024} KB", -1)
                
                signals.progress.emit("Extracting update...", 50)
                zip_data.seek(0)
                
                user_data_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ZYRA AI")
                update_dir = os.path.join(user_data_dir, "updates")
                os.makedirs(update_dir, exist_ok=True)
                
                with zipfile.ZipFile(zip_data) as zipf:
                    members = zipf.namelist()
                    total_members = len(members)
                    for i, member in enumerate(members):
                        if member.startswith("ZYRA-main/app/") or member.startswith("ZYRA-main/ai/"):
                            target_path = os.path.join(update_dir, member.replace("ZYRA-main/", ""))
                            if member.endswith('/'):
                                os.makedirs(target_path, exist_ok=True)
                            else:
                                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                                with zipf.open(member) as source, open(target_path, "wb") as target:
                                    shutil.copyfileobj(source, target)
                        
                        if i % 10 == 0:
                            pct = 50 + int((i / total_members) * 40)
                            signals.progress.emit(f"Extracting... {i}/{total_members}", pct)
                                    
                with open(os.path.join(user_data_dir, "current_version.json"), "w") as f:
                    json.dump(v_info, f)
                    
                signals.progress.emit("Finalizing...", 95)
                time.sleep(0.5)
                signals.finished.emit()
            except Exception as e:
                signals.error.emit(str(e))
                
        threading.Thread(target=worker, daemon=True).start()

    def _silent_update_check(self):
        import threading
        from PySide6.QtCore import QObject, Signal
        
        class UpdateSignals(QObject):
            new_update = Signal(dict)
            up_to_date = Signal()
            
        self._update_signals = UpdateSignals()
        signals = self._update_signals
        
        def on_new_update(v_info):
            pub_version = v_info.get("version", "")
            self.update_status_lbl.setText(f"🚀 New Update Available (Patch {pub_version})")
            self.update_status_lbl.setStyleSheet("color: #10b981; font-weight: bold;")
            
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(self, "Update Available", 
                                     f"New OTA Update found!\nDesc: {v_info.get('description')}\nNew Version: {pub_version}\n\nUpdate now?",
                                     QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                main_win = self.window()
                if hasattr(main_win, 'sidebar'):
                    main_win.sidebar.setCurrentRow(3) # Move to Settings page
                self._apply_update(v_info)
            
        def on_up_to_date():
            self.update_status_lbl.setText("App is up to date.")
            self.update_status_lbl.setStyleSheet("")
            
        signals.new_update.connect(on_new_update)
        signals.up_to_date.connect(on_up_to_date)
        
        def worker():
            import os, sys, json, requests, time
            user_data_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ZYRA AI")
            
            try:
                resp = requests.get(f"https://raw.githubusercontent.com/annabil-dev/ZYRA/main/publish/version.json?t={int(time.time())}", timeout=3)
                if resp.status_code == 200:
                    v_info = resp.json()
                    
                    current_version = "v1.0.81"
                    current_v_path = os.path.join(user_data_dir, "current_version.json")
                    if os.path.exists(current_v_path):
                        with open(current_v_path, 'r') as f:
                            current_version = json.load(f).get("version", "v1.0.81")
                            
                    pub_version = v_info.get("version", "v1.0.81")
                    
                    if self._parse_version(pub_version) > self._parse_version(current_version):
                        signals.new_update.emit(v_info)
                    else:
                        signals.up_to_date.emit()
            except Exception:
                pass
                
        threading.Thread(target=worker, daemon=True).start()

    def on_generation_error(self, err: str):
        self.send_btn.setEnabled(True)
        self.send_btn.setIcon(self.icon_send)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #38bdf8;
                color: #0f172a;
                border-radius: 12px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #7dd3fc; }
            QPushButton:disabled { background-color: #475569; color: #94a3b8; }
        """)
        msg = f"<font color='red'>Error: {err}</font>"
        self.chat_history_layout.addWidget(ChatBubbleWidget("ai", msg))
        self._scroll_to_bottom()
        self._active_generation_session_id = None

        # Trigger TTS if enabled
        if self.tts_btn.isChecked() and self._current_ai_response.strip():
            try:
                from app.workers.tts_worker import TTSWorker
                if self.tts_worker and self.tts_worker.isRunning():
                    self.tts_worker.stop()
                    self.tts_worker.wait()
                self.tts_worker = TTSWorker(self._current_ai_response, parent=self)
                self.tts_worker.start()
            except ImportError:
                print("TTS Disabled: edge-tts is not installed in this environment.")
            except Exception as e:
                print(f"TTS Error: {e}")


    def on_mic_clicked(self):
        """Toggles recording when the mic button is clicked."""
        if not self.voice_assistant:
            from app.core.voice import VoiceAssistant
            self.voice_assistant = VoiceAssistant()
            
        if not self.voice_assistant.is_recording:
            # Start Recording
            self.mic_btn.setIcon(self.icon_mic_rec)
            self.mic_btn.setStyleSheet("""
                QPushButton { background-color: transparent; border: none; border-radius: 18px; padding: 0px; }
                QPushButton:hover { background-color: #fee2e2; }
            """)
            self.input_field.setPlaceholderText("Merekam suara... (Klik lagi untuk stop)")
            self.input_field.setReadOnly(True)
            self.voice_assistant.start_recording()
        else:
            # Stop Recording
            self.mic_btn.setIcon(self.icon_mic)
            self.mic_btn.setStyleSheet("""
                QPushButton { background-color: transparent; border: none; border-radius: 18px; padding: 0px; }
                QPushButton:hover { background-color: #334155; }
            """)
            self.input_field.setPlaceholderText("Memproses suara...")
            
            from app.workers.voice_worker import VoiceWorker
            self.voice_worker = VoiceWorker(self.voice_assistant, parent=self)
            self.voice_worker.transcription_complete.connect(self.on_voice_transcribed)
            self.voice_worker.error_occurred.connect(self.on_voice_error)
            self.voice_worker.start()
        
    def on_voice_transcribed(self, text: str):
        self.input_field.setPlaceholderText("Message ZYRA...")
        self.input_field.setReadOnly(False)
        
        if text:
            # Append to existing text with a space, or just set it
            current = self.input_field.text()
            if current:
                self.input_field.setText(f"{current} {text}")
            else:
                self.input_field.setText(text)
                
            self.input_field.setFocus()
            
    def on_voice_error(self, err: str):
        self.input_field.setPlaceholderText("Message ZYRA...")
        self.input_field.setReadOnly(False)
        self.logger.error(f"Voice Error: {err}")
        self.show_toast("Gagal memproses suara. Pastikan PyTorch ter-install dengan benar.", type="error", duration=3000)

    def handle_security_check(self, tool_name: str, arguments_str: str):
        """Displays a confirmation dialog for dangerous tools."""
        from PySide6.QtWidgets import QMessageBox
        import json
        
        args = {}
        try:
            args = json.loads(arguments_str)
        except:
            pass
            
        msg = f"ZYRA AI is trying to use the '{tool_name}' tool.\n\n"
        if tool_name == "run_command":
            msg += f"Command:\n{args.get('command', '')}\n\nWorking Directory: {args.get('cwd', 'Default')}"
        elif tool_name == "write_file_content":
            msg += f"File:\n{args.get('path', '')}\n\nContent Length: {len(args.get('content', ''))} characters"
            
        msg += "\n\nDo you want to ALLOW this action?"
        
        reply = QMessageBox.question(
            self, 
            "Security Confirmation", 
            msg,
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        # Resume the worker with the decision
        allow = (reply == QMessageBox.Yes)
        if hasattr(self, 'worker') and self.worker:
            self.worker.set_security_response(allow)


