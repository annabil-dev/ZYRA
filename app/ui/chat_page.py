import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QTextEdit, QLineEdit, QLabel, QSlider, QSpinBox, 
                               QDoubleSpinBox, QGroupBox, QMessageBox, QFileDialog,
                               QComboBox, QListWidget, QListWidgetItem, QSplitter,
                               QScrollArea, QFrame)
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
        self.current_session_id = None
        self._current_ai_response = ""
        
        self.init_ui()
        self._load_sessions_from_db()
        
        # Auto-detect and connect to the best available Ollama model on startup
        QTimer.singleShot(300, self._auto_detect_and_connect)
        QTimer.singleShot(500, self._silent_update_check)
        
    def init_ui(self):
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
        chat_widget = OverlayChatWidget()
        chat_widget.setObjectName("ChatArea")
        splitter.addWidget(chat_widget)
        chat_layout = QVBoxLayout(chat_widget)
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
        
        model_layout.addStretch()
        input_layout.addLayout(model_layout)
        
        # Bottom part of input frame: Text input & Send button
        bottom_input_layout = QHBoxLayout()
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
        self.input_field.returnPressed.connect(self.start_generation)
        
        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("SendBtn")
        self.send_btn.setFixedWidth(80)
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
        self.send_btn.clicked.connect(self.on_send_click)
        
        bottom_input_layout.addWidget(self.input_field)
        bottom_input_layout.addWidget(self.send_btn)
        
        input_layout.addLayout(bottom_input_layout)
        
        # Overlay container for absolute positioning
        chat_widget.input_container = QWidget(chat_widget)
        chat_widget.input_container.setStyleSheet("background: transparent;")
        overlay_layout = QVBoxLayout(chat_widget.input_container)
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
        self.settings_widget.setFixedWidth(280)
        settings_layout = QVBoxLayout(self.settings_widget)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        
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
        
        # System Update Group
        update_group = QGroupBox("System Update")
        update_layout = QVBoxLayout()
        self.update_status_lbl = QLabel("App is up to date.")
        self.update_status_lbl.setWordWrap(True)
        self.check_update_btn = QPushButton("Check for Updates")
        self.check_update_btn.clicked.connect(self.check_for_updates)
        
        from PySide6.QtWidgets import QProgressBar
        self.update_progress = QProgressBar()
        self.update_progress.setVisible(False)
        
        update_layout.addWidget(self.update_status_lbl)
        update_layout.addWidget(self.update_progress)
        update_layout.addWidget(self.check_update_btn)
        update_group.setLayout(update_layout)
        
        settings_layout.addWidget(backend_group)
        settings_layout.addWidget(load_group)
        settings_layout.addWidget(param_group)
        settings_layout.addWidget(update_group)
        settings_layout.addStretch()
        
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
            self.send_btn.setText("Send")
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
                self.send_btn.setText("Stop")
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
            self.send_btn.setText("Send")
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
        
        if not quiet:
            self.status_lbl.setText("Status: Auto-detecting models...")
        self.repaint()
        
        try:
            resp = httpx.get("http://localhost:11434/api/tags", timeout=0.5)
            if resp.status_code != 200:
                if not quiet:
                    self.status_lbl.setText("Status: Ollama not responding")
                return
            
            data = resp.json()
            installed_tags = {m["name"] for m in data.get("models", [])}
            
            # Match installed models against our priority list (best last)
            matched = []
            for display_name, tag, size_gb in MODEL_PRIORITY:
                # Ollama tags may include ':latest' suffix
                tag_variants = [tag, tag + ":latest", tag.split(":")[0] + ":latest"]
                if any(t in installed_tags for t in tag_variants):
                    matched.append((display_name, tag, size_gb))
            
            # Also add any installed models NOT in our priority list
            known_tags = {tag for _, tag, _ in MODEL_PRIORITY}
            for installed_tag in installed_tags:
                base = installed_tag.replace(":latest", "")
                if base not in known_tags and installed_tag not in known_tags:
                    matched.append((installed_tag, base, 0))
            
            if not matched:
                if not quiet:
                    self.status_lbl.setText("Status: No Ollama models found")
                    self.show_toast("No models installed in Ollama. Pull a model first: ollama pull qwen2.5:32b", type="warning", duration=8000)
                return
            
            # Populate dropdown — best model last in list, but first in combo
            matched.sort(key=lambda x: x[2], reverse=True)
            
            # Temporarily disconnect to avoid triggering load_model on clear
            self.ollama_model_combo.currentIndexChanged.disconnect(self.load_model)
            self.ollama_model_combo.clear()
            for display_name, tag, size in matched:
                self.ollama_model_combo.addItem(f"{display_name}", userData=tag)
            self.ollama_model_combo.currentIndexChanged.connect(self.load_model)
            
            # Auto-connect
            best_name, best_tag, best_size = matched[0]
            if not quiet:
                self.show_toast(f"Auto-detected {len(matched)} installed model(s). Best available: {best_name} ({best_size:.0f} GB)", type="info")
                
            self._load_ollama_model(quiet=quiet)
            
        except Exception as e:
            if not quiet:
                self.status_lbl.setText("Status: Ollama offline. Retrying...")
                if not hasattr(self, '_ollama_offline_warned'):
                    self.show_toast("Could not reach Ollama engine. Auto-retrying in the background...", type="warning")
                    self._ollama_offline_warned = True
                QTimer.singleShot(5000, self._auto_detect_and_connect)

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
            try:
                resp = httpx.get("http://localhost:11434", timeout=0.5)
                if resp.status_code == 200:
                    if not quiet:
                        self.status_lbl.setText(f"Status: Connected — {display_name}")
                        self.show_toast(f"Connected to local Ollama engine. Model: {model_tag}. Ready to generate.", type="success")
                else:
                    raise ConnectionError(f"Ollama returned status {resp.status_code}")
            except Exception:
                if not quiet:
                    self.status_lbl.setText(f"Status: Ollama offline — will retry on send")
                    self.show_toast(f"Warning: Ollama offline at localhost. Model set to {model_tag}. Will auto-retry on send.", type="warning", duration=8000)
            
            self.load_btn.setEnabled(True)
            
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

    def start_generation(self):
        if not self.generator:
            QMessageBox.warning(self, "Warning", "Please load or connect to a model first.")
            return
            
        prompt = self.input_field.text().strip()
        if not prompt:
            return
            
        # 1. Database - Create new session if none exists
        if self.current_session_id is None and self.db_manager and self.db_manager.connection:
            cursor = self.db_manager.connection.cursor()
            title = prompt[:30] + "..." if len(prompt) > 30 else prompt
            model_tag = self.ollama_model_combo.currentData() or self.ollama_model_combo.currentText()
            cursor.execute("INSERT INTO chat_sessions (title, model_name) VALUES (?, ?)", (title, model_tag))
            self.current_session_id = cursor.lastrowid
            self.db_manager.connection.commit()
            self._load_sessions_from_db() # Refresh sidebar
            
        # 2. Database - Save user message
        if self.db_manager and self.db_manager.connection and self.current_session_id:
            cursor = self.db_manager.connection.cursor()
            cursor.execute("INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)", 
                           (self.current_session_id, "user", prompt))
            cursor.execute("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (self.current_session_id,))
            self.db_manager.connection.commit()
            
        # Append user prompt with right-aligned bubble
        user_bubble = ChatBubbleWidget("user", prompt)
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
                # Don't include the current prompt we just saved
                history_msgs.append({"role": r, "content": c})
            # Remove the last user message because we pass it as 'prompt'
            if history_msgs and history_msgs[-1]["role"] == "user":
                history_msgs.pop()
        
        
        self.send_btn.setText("Stop")
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
            prompt=prompt,
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
        self.send_btn.setText("Send")
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

    def _parse_version(self, v):
        try:
            return tuple(map(int, str(v).replace('v', '').split('.')))
        except:
            return (0, 0, 0)

    def check_for_updates(self):
        import os, sys, json, time, zipfile, shutil
        # For simulation, check local publish folder. Real apps check a URL.
        if getattr(sys, 'frozen', False):
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(sys.executable)))
        else:
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
        publish_dir = os.path.join(root_dir, "publish")
        version_path = os.path.join(publish_dir, "version.json")
        zip_path = os.path.join(publish_dir, "update.zip")
        
        if not os.path.exists(version_path):
            QMessageBox.information(self, "Updater", "No updates found. You are on the latest version.")
            return
            
        with open(version_path, 'r') as f:
            v_info = json.load(f)
            
        if getattr(sys, 'frozen', False):
            user_data_dir = os.path.dirname(sys.executable)
        else:
            user_data_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
        current_version = "v0.0.0"
        current_v_path = os.path.join(user_data_dir, "current_version.json")
        if os.path.exists(current_v_path):
            try:
                with open(current_v_path, 'r') as f:
                    current_version = json.load(f).get("version", "v0.0.0")
            except Exception:
                pass
                
        pub_version = v_info.get("version", "v0.0.0")
        if self._parse_version(pub_version) <= self._parse_version(current_version) and current_version != "v0.0.0":
            QMessageBox.information(self, "Updater", "You are already on the latest version.")
            return
            
        reply = QMessageBox.question(self, "Update Available", 
                                     f"New source code update found!\nDesc: {v_info.get('description')}\nPatch: {pub_version}\nUpdate now?",
                                     QMessageBox.Yes | QMessageBox.No)
                                     
        if reply == QMessageBox.Yes:
            self._apply_update(zip_path, v_info)
            
    def _apply_update(self, zip_path, v_info):
        import os, sys, time, zipfile, json
        self.update_progress.setVisible(True)
        self.update_progress.setRange(0, 100)
        self.update_status_lbl.setText("Downloading and extracting...")
        self.check_update_btn.setEnabled(False)
        self.repaint()
        
        # Simulate download delay
        for i in range(101):
            self.update_progress.setValue(i)
            time.sleep(0.01)
            self.repaint()
            
        # Extract
        if getattr(sys, 'frozen', False):
            user_data_dir = os.path.dirname(sys.executable)
        else:
            user_data_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
        update_dir = os.path.join(user_data_dir, "updates")
        os.makedirs(update_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            zipf.extractall(update_dir)
            
        with open(os.path.join(user_data_dir, "current_version.json"), "w") as f:
            json.dump(v_info, f)
            
        self.update_status_lbl.setText("Update complete. Restarting...")
        self.repaint()
        time.sleep(1)
        
        # Restart the app
        exe_path = sys.executable
        if getattr(sys, 'frozen', False):
            os.execv(exe_path, [exe_path])
        else:
            run_script = os.path.join(user_data_dir, "run.py")
            os.execv(exe_path, [exe_path, run_script])

    def _silent_update_check(self):
        import os, sys, json
        if getattr(sys, 'frozen', False):
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(sys.executable)))
            user_data_dir = os.path.dirname(sys.executable)
        else:
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            user_data_dir = root_dir
            
        publish_dir = os.path.join(root_dir, "publish")
        version_path = os.path.join(publish_dir, "version.json")
        
        if os.path.exists(version_path):
            try:
                with open(version_path, 'r') as f:
                    v_info = json.load(f)
                
                current_version = "v0.0.0"
                current_v_path = os.path.join(user_data_dir, "current_version.json")
                if os.path.exists(current_v_path):
                    with open(current_v_path, 'r') as f:
                        current_version = json.load(f).get("version", "v0.0.0")
                        
                pub_version = v_info.get("version", "v0.0.0")
                
                if self._parse_version(pub_version) > self._parse_version(current_version):
                    self.update_status_lbl.setText(f"🚀 New Update Available (Patch {pub_version})")
                    self.update_status_lbl.setStyleSheet("color: #10b981; font-weight: bold;")
                else:
                    self.update_status_lbl.setText("App is up to date.")
                    self.update_status_lbl.setStyleSheet("")
            except Exception:
                pass

    def on_generation_error(self, err: str):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Send")
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
