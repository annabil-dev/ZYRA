from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFormLayout, QFrame, QHBoxLayout
from PySide6.QtCore import Qt

class DashboardPage(QWidget):
    def __init__(self, hardware_info: dict):
        super().__init__()
        self.hardware_info = hardware_info
        self.init_ui()

    def create_row(self, label_text: str, value_text: str) -> QHBoxLayout:
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setObjectName("LabelKey")
        val = QLabel(value_text)
        val.setObjectName("LabelValue")
        row.addWidget(lbl)
        row.addWidget(val)
        row.addStretch()
        return row

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        title = QLabel("MY-AI Dashboard")
        title.setObjectName("Header")
        layout.addWidget(title)

        # System Status Group
        sys_card = QFrame()
        sys_card.setObjectName("Card")
        sys_layout = QVBoxLayout(sys_card)
        
        sys_title = QLabel("System Status")
        sys_title.setObjectName("CardTitle")
        sys_layout.addWidget(sys_title)
        
        sys_layout.addLayout(self.create_row("OS:", self.hardware_info.get("os", "Unknown")))
        sys_layout.addLayout(self.create_row("CPU:", self.hardware_info.get("cpu", "Unknown")))
        sys_layout.addLayout(self.create_row("RAM (GB):", str(self.hardware_info.get("ram_total_gb", "Unknown"))))
        sys_layout.addLayout(self.create_row("GPU:", self.hardware_info.get("gpu", "Unknown")))
        sys_layout.addLayout(self.create_row("VRAM (GB):", str(self.hardware_info.get("vram_gb", "Unknown"))))
        sys_layout.addLayout(self.create_row("CUDA Available:", "Yes" if self.hardware_info.get("cuda_available") else "No"))
        sys_layout.addLayout(self.create_row("CUDA Version:", self.hardware_info.get("cuda_version", "N/A")))
        sys_layout.addLayout(self.create_row("PyTorch Version:", self.hardware_info.get("pytorch_version", "N/A")))
        
        layout.addWidget(sys_card)

        # Application Status Group
        app_card = QFrame()
        app_card.setObjectName("Card")
        app_layout = QVBoxLayout(app_card)
        
        app_title = QLabel("Application Status")
        app_title.setObjectName("CardTitle")
        app_layout.addWidget(app_title)
        
        app_layout.addLayout(self.create_row("AI Engine:", "Not initialized"))
        app_layout.addLayout(self.create_row("Model:", "No model loaded"))
        app_layout.addLayout(self.create_row("Training:", "Idle"))
        
        layout.addWidget(app_card)
        layout.addStretch()
