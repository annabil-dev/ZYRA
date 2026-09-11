from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QStackedWidget
from PySide6.QtGui import QIcon
from app.ui.dashboard_page import DashboardPage
from app.ui.logs_page import LogsPage
from app.ui.placeholders import PlaceholderPage
from app.ui.chat_page import ChatPage
from app.ui.settings_page import SettingsPage
from app.ui.models_page import ModelsPage
import os
import sys

class MainWindow(QMainWindow):
    def __init__(self, hardware_info: dict, log_file_path: str, db_manager=None):
        super().__init__()
        self.hardware_info = hardware_info
        self.log_file_path = log_file_path
        self.db_manager = db_manager
        
        self.setWindowTitle("ZYRA")
        self.resize(1200, 800)
        
        # Set Window Icon
        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            
        icon_path = os.path.join(base_dir, "app", "ui", "icon.ico")
        self.setWindowIcon(QIcon(icon_path))

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(220)
        
        sidebar_items = ["Dashboard", "Chat", "Dataset", "Training", "Models", "Settings"]
        self.sidebar.addItems(sidebar_items)
        
        # Pages Container
        self.pages = QStackedWidget()
        self.pages.setObjectName("PagesContainer")
        
        self.dashboard_page = DashboardPage(self.hardware_info)
        self.chat_page = ChatPage(db_manager=self.db_manager)
        self.dataset_page = PlaceholderPage("Dataset")
        self.training_page = PlaceholderPage("Training")
        self.models_page = ModelsPage(self.hardware_info, self.chat_page)
        self.settings_page = SettingsPage(self.chat_page)
        # self.logs_page = LogsPage(self.log_file_path)
        
        self.pages.addWidget(self.dashboard_page)
        self.pages.addWidget(self.chat_page)
        self.pages.addWidget(self.dataset_page)
        self.pages.addWidget(self.training_page)
        self.pages.addWidget(self.models_page)
        self.pages.addWidget(self.settings_page)
        # self.pages.addWidget(self.logs_page)
        
        self.sidebar.currentRowChanged.connect(self.pages.setCurrentIndex)
        
        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.pages)
        
        self.setup_hot_reload()

    def setup_hot_reload(self):
        """Monitors the project directories for code changes and prompts for restart."""
        import os
        from PySide6.QtCore import QFileSystemWatcher, QTimer
        
        self.watcher = QFileSystemWatcher(self)
        self.reload_timer = QTimer(self)
        self.reload_timer.setSingleShot(True)
        self.reload_timer.timeout.connect(self.show_update_dialog)
        
        # Directories to watch
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        watch_dirs = [
            os.path.join(base_dir, "app"),
            os.path.join(base_dir, "ai")
        ]
        
        # Add all subdirectories recursively
        for d in watch_dirs:
            for root, dirs, files in os.walk(d):
                self.watcher.addPath(root)
                for f in files:
                    if f.endswith(('.py', '.qss')):
                        self.watcher.addPath(os.path.join(root, f))
                
        self.watcher.fileChanged.connect(self.on_file_changed)
        self.watcher.directoryChanged.connect(self.on_file_changed)
        
    def on_file_changed(self, path):
        # Debounce the prompt so it doesn't pop up 10 times for one save
        if not self.reload_timer.isActive():
            self.reload_timer.start(1000) # Wait 1 second before showing dialog

    def show_update_dialog(self):
        from PySide6.QtWidgets import QMessageBox, QApplication
        import sys
        import os
        import subprocess
        
        reply = QMessageBox.question(
            self, 
            "Update Sistem Terdeteksi", 
            "Update kode baru saja diterapkan di background.\n\nApakah Anda ingin me-restart aplikasi sekarang untuk memuat update tersebut?",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            # Safely restart the application
            if self.db_manager:
                self.db_manager.close()
            
            # Start a new instance safely handling spaces in paths
            if getattr(sys, 'frozen', False):
                # When compiled, sys.executable is the .exe itself
                exe_path = sys.executable
                os.execv(exe_path, [exe_path])
            else:
                python_exe = sys.executable
                run_script = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "run.py")
                # Use os.execv to replace the current process entirely. This avoids child-process termination issues.
                os.execv(python_exe, [python_exe, run_script])

