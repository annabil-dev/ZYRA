import requests
import json
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QStackedWidget, QScrollArea, QGridLayout,
                               QProgressBar)
from PySide6.QtCore import Qt, QThread, Signal, QTimer

from app.ui.model_card import ModelCardWidget
from app.workers.ollama_installer import OllamaInstallerWorker

CURATED_MODELS = [
    {
        "name": "Llama 3.1 (8B)",
        "tag": "llama3.1:8b",
        "params": "8B",
        "required_ram": 6,
        "description": "Meta's highly capable 8B model. Best for general purpose tasks, writing, and chatting. Extremely fast."
    },
    {
        "name": "Qwen 2.5 (7B)",
        "tag": "qwen2.5:7b",
        "params": "7B",
        "required_ram": 6,
        "description": "Alibaba's latest model. Unbelievably smart for its size, especially in mathematics and logic."
    },
    {
        "name": "Mistral NeMo (12B)",
        "tag": "mistral-nemo",
        "params": "12B",
        "required_ram": 8,
        "description": "NVIDIA & Mistral collaboration. 128k context window. Perfect for document analysis and long chats."
    },
    {
        "name": "Phi-3 Medium (14B)",
        "tag": "phi3:medium",
        "params": "14B",
        "required_ram": 10,
        "description": "Microsoft's flagship reasoning model. Excels at step-by-step logic and academic tasks."
    },
    {
        "name": "DeepSeek Coder V2 (16B)",
        "tag": "deepseek-coder-v2",
        "params": "16B",
        "required_ram": 12,
        "description": "The absolute best coding assistant model for local machines. Beats many larger models in programming."
    },
    {
        "name": "Qwen 2.5 (32B)",
        "tag": "qwen2.5:32b",
        "params": "32B",
        "required_ram": 20,
        "description": "Heavyweight champion. Requires a powerful GPU but provides GPT-4 level intelligence."
    }
]

class OllamaPullWorker(QThread):
    progress_update = Signal(str, int, str)
    
    def __init__(self, tag):
        super().__init__()
        self.tag = tag
        
    def run(self):
        try:
            with requests.post("http://localhost:11434/api/pull", json={"name": self.tag}, stream=True) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if line:
                        data = json.loads(line)
                        status = data.get("status", "")
                        completed = data.get("completed", 0)
                        total = data.get("total", 1)
                        if total > 0:
                            percent = int((completed / total) * 100)
                        else:
                            percent = 0
                            
                        if "downloading" in status.lower() and total > 0:
                            self.progress_update.emit(self.tag, percent, status)
                        elif "success" in status.lower():
                            self.progress_update.emit(self.tag, 100, "Done")
                        else:
                            self.progress_update.emit(self.tag, percent, status)
                            
            self.progress_update.emit(self.tag, -2, "Success")
        except Exception as e:
            self.progress_update.emit(self.tag, -1, str(e))

class ModelsPage(QWidget):
    def __init__(self, hardware_info, chat_page=None):
        super().__init__()
        self.hardware_info = hardware_info
        self.chat_page = chat_page
        self.active_workers = {}
        self.cards = {}
        
        self.init_ui()
        
        # Initial check
        QTimer.singleShot(500, self.check_ollama_status)
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.stack = QStackedWidget()
        
        # State 1: Missing Ollama
        self.missing_page = QWidget()
        missing_layout = QVBoxLayout(self.missing_page)
        missing_layout.setAlignment(Qt.AlignCenter)
        
        icon_lbl = QLabel("🔌")
        icon_lbl.setStyleSheet("font-size: 64px;")
        icon_lbl.setAlignment(Qt.AlignCenter)
        
        title_lbl = QLabel("AI Engine Required")
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: white; margin-top: 20px;")
        title_lbl.setAlignment(Qt.AlignCenter)
        
        desc_lbl = QLabel("ZYRA requires the Ollama Engine to run local models.\nWe can download and install it for you automatically.")
        desc_lbl.setStyleSheet("color: #a3a3a3; font-size: 14px; text-align: center;")
        desc_lbl.setAlignment(Qt.AlignCenter)
        
        self.install_btn = QPushButton("Install Ollama Engine")
        self.install_btn.setFixedWidth(200)
        self.install_btn.setStyleSheet("""
            QPushButton { background-color: #2563eb; color: white; border: none; padding: 12px; border-radius: 8px; font-weight: bold; font-size: 14px;}
            QPushButton:hover { background-color: #3b82f6; }
            QPushButton:disabled { background-color: #475569; color: #94a3b8; }
        """)
        self.install_btn.clicked.connect(self.start_ollama_installation)
        
        self.install_progress = QProgressBar()
        self.install_progress.setFixedWidth(400)
        self.install_progress.setVisible(False)
        self.install_progress.setStyleSheet("""
            QProgressBar { border: 1px solid #2f2f2f; border-radius: 6px; text-align: center; color: white; background-color: #171717; }
            QProgressBar::chunk { background-color: #10b981; border-radius: 5px; }
        """)
        
        self.install_status = QLabel("")
        self.install_status.setStyleSheet("color: #a3a3a3; font-size: 12px;")
        self.install_status.setAlignment(Qt.AlignCenter)
        
        missing_layout.addWidget(icon_lbl)
        missing_layout.addWidget(title_lbl)
        missing_layout.addWidget(desc_lbl)
        
        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignCenter)
        btn_layout.addWidget(self.install_btn)
        missing_layout.addLayout(btn_layout)
        
        prog_layout = QHBoxLayout()
        prog_layout.setAlignment(Qt.AlignCenter)
        prog_layout.addWidget(self.install_progress)
        missing_layout.addLayout(prog_layout)
        
        missing_layout.addWidget(self.install_status)
        
        # State 2: Catalog Page
        self.catalog_page = QWidget()
        catalog_layout = QVBoxLayout(self.catalog_page)
        catalog_layout.setContentsMargins(40, 40, 40, 40)
        
        cat_header = QLabel("Model App Store")
        cat_header.setStyleSheet("font-size: 28px; font-weight: bold; color: white; margin-bottom: 10px;")
        
        cat_desc = QLabel("Hardware-aware recommendations based on your system specs.")
        cat_desc.setStyleSheet("color: #a3a3a3; font-size: 14px; margin-bottom: 20px;")
        
        catalog_layout.addWidget(cat_header)
        catalog_layout.addWidget(cat_desc)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; } QScrollArea viewport { background: transparent; }")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        self.grid_layout = QGridLayout(scroll_content)
        self.grid_layout.setSpacing(20)
        
        scroll.setWidget(scroll_content)
        catalog_layout.addWidget(scroll)
        
        self.stack.addWidget(self.missing_page)
        self.stack.addWidget(self.catalog_page)
        
        layout.addWidget(self.stack)

    def check_ollama_status(self):
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=1.0)
            if r.status_code == 200:
                installed_tags = [m["name"] for m in r.json().get("models", [])]
                self.populate_catalog(installed_tags)
                self.stack.setCurrentWidget(self.catalog_page)
                return
        except Exception:
            pass
            
        # Ollama API is not responding. Check if it's installed.
        import shutil, os, subprocess
        ollama_path = shutil.which("ollama")
        if not ollama_path:
            # Check default install path
            default_path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
            if os.path.exists(default_path):
                ollama_path = default_path
                
        if ollama_path:
            # It's installed but not running. Let's try to start it.
            self.install_status.setText("Ollama detected. Starting engine...")
            self.install_btn.setEnabled(False)
            self.stack.setCurrentWidget(self.missing_page)
            try:
                # CREATE_NO_WINDOW is 0x08000000 on Windows
                subprocess.Popen([ollama_path, "serve"], creationflags=0x08000000)
                # Wait a bit and check again
                from PySide6.QtCore import QTimer
                QTimer.singleShot(2000, self._retry_check_after_start)
            except Exception as e:
                self.install_status.setText(f"Failed to start Ollama: {e}")
            return

        self.install_status.setText("")
        self.install_btn.setEnabled(True)
        self.stack.setCurrentWidget(self.missing_page)

    def _retry_check_after_start(self):
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=1.0)
            if r.status_code == 200:
                installed_tags = [m["name"] for m in r.json().get("models", [])]
                self.populate_catalog(installed_tags)
                self.stack.setCurrentWidget(self.catalog_page)
                return
        except Exception:
            self.install_status.setText("Failed to connect to Ollama after starting. Please run it manually.")

    def populate_catalog(self, installed_tags):
        # Clear existing
        for i in reversed(range(self.grid_layout.count())): 
            self.grid_layout.itemAt(i).widget().setParent(None)
            
        self.cards.clear()
        
        row, col = 0, 0
        for info in CURATED_MODELS:
            is_installed = any(info["tag"] in tag or tag in info["tag"] for tag in installed_tags)
            
            card = ModelCardWidget(info, self.hardware_info, is_installed)
            card.download_clicked.connect(self.on_download_clicked)
            card.delete_clicked.connect(self.on_delete_clicked)
            
            self.cards[info["tag"]] = card
            self.grid_layout.addWidget(card, row, col)
            
            col += 1
            if col > 1: # 2 columns
                col = 0
                row += 1

    def start_ollama_installation(self):
        self.install_btn.setEnabled(False)
        self.install_btn.setText("Installing...")
        self.install_progress.setVisible(True)
        self.install_progress.setValue(0)
        
        self.installer_worker = OllamaInstallerWorker()
        self.installer_worker.progress_update.connect(self.update_install_progress)
        self.installer_worker.finished.connect(self.on_install_finished)
        self.installer_worker.start()

    def update_install_progress(self, percent, msg):
        self.install_progress.setValue(percent)
        self.install_status.setText(msg)

    def on_install_finished(self, success, msg):
        if success:
            self.check_ollama_status()
        else:
            self.install_status.setText(f"Failed: {msg}")
            self.install_btn.setEnabled(True)
            self.install_btn.setText("Retry Installation")
            self.install_progress.setVisible(False)

    def on_download_clicked(self, tag):
        worker = OllamaPullWorker(tag)
        worker.progress_update.connect(self.update_card_progress)
        self.active_workers[tag] = worker
        worker.start()

    def update_card_progress(self, tag, percent, status):
        if tag in self.cards:
            self.cards[tag].update_progress(percent, status)
            
        if percent < 0 and tag in self.active_workers:
            del self.active_workers[tag]
            
        if percent == -2 and self.chat_page:
            # Download finished successfully! Auto-refresh the chat page dropdown.
            self.chat_page._auto_detect_and_connect(quiet=True)

    def on_delete_clicked(self, tag):
        try:
            requests.delete("http://localhost:11434/api/delete", json={"name": tag})
            # Refresh catalog
            self.check_ollama_status()
            if self.chat_page:
                self.chat_page._auto_detect_and_connect(quiet=True)
        except:
            pass
