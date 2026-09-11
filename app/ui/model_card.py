from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QFrame, QProgressBar, QSizePolicy)
from PySide6.QtCore import Qt, Signal

class ModelCardWidget(QFrame):
    download_clicked = Signal(str) # emits model tag
    delete_clicked = Signal(str) # emits model tag

    def __init__(self, model_info, hardware_info, is_installed=False):
        super().__init__()
        self.model_info = model_info
        self.hardware_info = hardware_info
        self.is_installed = is_installed
        
        self.setObjectName("ModelCard")
        self.setStyleSheet("""
            QFrame#ModelCard {
                background-color: #212121;
                border: 1px solid #2f2f2f;
                border-radius: 12px;
            }
            QFrame#ModelCard:hover {
                border: 1px solid #3b82f6;
            }
        """)
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # --- Top Row: Title & Badge ---
        top_layout = QHBoxLayout()
        
        title_lbl = QLabel(self.model_info["name"])
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: white;")
        top_layout.addWidget(title_lbl)
        
        # Calculate Hardware Recommendation
        badge_lbl = QLabel()
        badge_lbl.setAlignment(Qt.AlignCenter)
        
        vram = self.hardware_info.get("vram_gb", 0)
        ram = self.hardware_info.get("ram_total_gb", 0)
        total_mem = vram + (ram * 0.8) # 80% of RAM is usable
        
        req_mem = self.model_info["required_ram"]
        
        if total_mem < req_mem:
            rec_text = "Not Recommended"
            rec_color = "#ef4444" # Red
            rec_bg = "#450a0a"
        elif vram >= req_mem:
            rec_text = "Highly Recommended"
            rec_color = "#10b981" # Green
            rec_bg = "#064e3b"
        else:
            rec_text = "Playable"
            rec_color = "#f59e0b" # Yellow
            rec_bg = "#78350f"
            
        badge_lbl.setText(rec_text)
        badge_lbl.setStyleSheet(f"""
            QLabel {{
                color: {rec_color};
                background-color: {rec_bg};
                padding: 4px 8px;
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
            }}
        """)
        top_layout.addStretch()
        top_layout.addWidget(badge_lbl)
        
        layout.addLayout(top_layout)
        
        # --- Middle Row: Description & Specs ---
        desc_lbl = QLabel(self.model_info["description"])
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #a3a3a3; font-size: 13px; margin-top: 8px; margin-bottom: 8px;")
        desc_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(desc_lbl)
        
        specs_layout = QHBoxLayout()
        
        size_lbl = QLabel(f"Size: {self.model_info['params']} Parameters")
        size_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        
        req_lbl = QLabel(f"Req. RAM: ~{req_mem}GB")
        req_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        
        specs_layout.addWidget(size_lbl)
        specs_layout.addStretch()
        specs_layout.addWidget(req_lbl)
        
        layout.addLayout(specs_layout)
        
        # --- Bottom Row: Actions & Progress ---
        self.action_layout = QHBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #2f2f2f;
                border-radius: 6px;
                text-align: center;
                color: white;
                background-color: #171717;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
                border-radius: 5px;
            }
        """)
        
        self.action_btn = QPushButton()
        if self.is_installed:
            self.action_btn.setText("Uninstall")
            self.action_btn.setStyleSheet("""
                QPushButton { background-color: #ef4444; color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: bold; }
                QPushButton:hover { background-color: #dc2626; }
            """)
            self.action_btn.clicked.connect(lambda: self.delete_clicked.emit(self.model_info["tag"]))
        else:
            self.action_btn.setText("Download")
            self.action_btn.setStyleSheet("""
                QPushButton { background-color: #2563eb; color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: bold; }
                QPushButton:hover { background-color: #3b82f6; }
            """)
            self.action_btn.clicked.connect(self.start_download)
            
        self.action_layout.addWidget(self.progress_bar)
        self.action_layout.addWidget(self.action_btn)
        
        layout.addLayout(self.action_layout)

    def start_download(self):
        self.action_btn.setEnabled(False)
        self.action_btn.setText("Downloading...")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.download_clicked.emit(self.model_info["tag"])
        
    def update_progress(self, percent, status_text=""):
        if percent < 0:
            # Error or finished
            self.progress_bar.setVisible(False)
            self.action_btn.setEnabled(True)
            self.action_btn.setText("Download Failed" if percent == -1 else "Installed")
            if percent == -2: # Success
                self.is_installed = True
                self.action_btn.setText("Uninstall")
                self.action_btn.setStyleSheet("""
                    QPushButton { background-color: #ef4444; color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: bold; }
                    QPushButton:hover { background-color: #dc2626; }
                """)
                # Disconnect old and connect new
                try: self.action_btn.clicked.disconnect() 
                except: pass
                self.action_btn.clicked.connect(lambda: self.delete_clicked.emit(self.model_info["tag"]))
        else:
            self.progress_bar.setValue(percent)
            if status_text:
                self.progress_bar.setFormat(f"%p% - {status_text}")
            else:
                self.progress_bar.setFormat("%p%")
