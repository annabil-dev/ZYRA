from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QFrame, 
                                 QHBoxLayout, QGridLayout)
from PySide6.QtCore import Qt

class DashboardPage(QWidget):
    def __init__(self, hardware_info: dict):
        super().__init__()
        self.hardware_info = hardware_info
        self.init_ui()

    def create_stat_pill(self, icon: str, title: str, value: str) -> QFrame:
        pill = QFrame()
        pill.setObjectName("StatPill")
        layout = QHBoxLayout(pill)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        
        icon_lbl = QLabel()
        icon_lbl.setStyleSheet("background: transparent;")
        icon_lbl.setFixedWidth(36)
        icon_lbl.setAlignment(Qt.AlignCenter)
        
        import os, sys
        from PySide6.QtGui import QIcon, QPixmap
        
        assets_dir = os.path.join(os.path.dirname(__file__), "assets", "icons")
        if getattr(sys, 'frozen', False):
            meipass_dir = os.path.join(sys._MEIPASS, "app", "ui", "assets", "icons")
            if os.path.exists(meipass_dir):
                assets_dir = meipass_dir
            
        icon_path = os.path.join(assets_dir, icon)
        
        # Load SVG
        if os.path.exists(icon_path):
            pixmap = QIcon(icon_path).pixmap(28, 28)
            icon_lbl.setPixmap(pixmap)
        else:
            icon_lbl.setText("?")
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        
        title_lbl = QLabel(title)
        title_lbl.setObjectName("CardSubtitle")
        title_lbl.setStyleSheet("margin-bottom: 0px;")
        
        val_lbl = QLabel(value)
        val_lbl.setObjectName("CardTitle")
        val_lbl.setStyleSheet("margin-bottom: 0px; font-size: 16px;")
        
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(val_lbl)
        
        layout.addWidget(icon_lbl)
        layout.addLayout(text_layout)
        layout.addStretch()
        
        return pill

    def create_row(self, label_text: str, value_text: str, status_color: str = None) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 4, 0, 4)
        lbl = QLabel(label_text)
        lbl.setObjectName("LabelKey")
        val = QLabel(value_text)
        val.setObjectName("LabelValue")
        
        if status_color:
            val.setStyleSheet(f"color: {status_color}; font-weight: 700;")
            
        row.addWidget(lbl)
        row.addWidget(val)
        row.addStretch()
        return row

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(32)

        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        
        title = QLabel("Dashboard")
        title.setObjectName("Header")
        
        subtitle = QLabel("System overview and AI engine status")
        subtitle.setObjectName("CardSubtitle")
        
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addLayout(header_layout)

        # 1. Hardware Grid
        grid = QGridLayout()
        grid.setSpacing(20)
        
        os_name = self.hardware_info.get("os", "Unknown")
        cpu_name = self.hardware_info.get("cpu", "Unknown")
        # Truncate CPU name if too long
        if len(cpu_name) > 30:
            cpu_name = cpu_name[:27] + "..."
            
        ram_gb = str(self.hardware_info.get("ram_total_gb", "Unknown"))
        gpu_name = self.hardware_info.get("gpu", "Unknown")
        vram_gb = str(self.hardware_info.get("vram_gb", "Unknown"))
        
        # Pill 1: OS
        pill_os = self.create_stat_pill("monitor.svg", "Operating System", os_name)
        # Pill 2: CPU
        pill_cpu = self.create_stat_pill("cpu.svg", "Processor", cpu_name)
        # Pill 3: RAM
        pill_ram = self.create_stat_pill("memory.svg", "System Memory", f"{ram_gb} GB RAM")
        # Pill 4: GPU
        pill_gpu = self.create_stat_pill("gpu.svg", "Graphics Card", f"{gpu_name} ({vram_gb} GB VRAM)")
        
        grid.addWidget(pill_os, 0, 0)
        grid.addWidget(pill_cpu, 0, 1)
        grid.addWidget(pill_ram, 1, 0)
        grid.addWidget(pill_gpu, 1, 1)
        
        layout.addLayout(grid)

        # 2. Advanced System Info & Application Status
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(20)
        
        # App Status Card
        app_card = QFrame()
        app_card.setObjectName("Card")
        app_layout = QVBoxLayout(app_card)
        app_layout.setSpacing(12)
        
        app_title = QLabel("Application Status")
        app_title.setObjectName("CardTitle")
        app_layout.addWidget(app_title)
        
        # We can simulate active/inactive colors here
        app_layout.addLayout(self.create_row("AI Engine:", "Standby", "#a1a1aa"))
        app_layout.addLayout(self.create_row("Loaded Model:", "None", "#a1a1aa"))
        app_layout.addLayout(self.create_row("Background Tasks:", "Idle", "#10b981")) # Emerald
        
        bottom_layout.addWidget(app_card)
        
        # Frameworks Card
        fw_card = QFrame()
        fw_card.setObjectName("Card")
        fw_layout = QVBoxLayout(fw_card)
        fw_layout.setSpacing(12)
        
        fw_title = QLabel("Frameworks")
        fw_title.setObjectName("CardTitle")
        fw_layout.addWidget(fw_title)
        
        cuda_avail = self.hardware_info.get("cuda_available")
        cuda_text = "Available" if cuda_avail else "Not Available"
        cuda_color = "#10b981" if cuda_avail else "#ef4444"
        
        fw_layout.addLayout(self.create_row("CUDA Acceleration:", cuda_text, cuda_color))
        fw_layout.addLayout(self.create_row("CUDA Version:", self.hardware_info.get("cuda_version", "N/A")))
        fw_layout.addLayout(self.create_row("PyTorch Version:", self.hardware_info.get("pytorch_version", "N/A")))
        
        bottom_layout.addWidget(fw_card)
        
        layout.addLayout(bottom_layout)
        layout.addStretch()
