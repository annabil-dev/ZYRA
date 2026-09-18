from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QStackedWidget
from PySide6.QtGui import QIcon
from app.ui.dashboard_page import DashboardPage
from app.ui.logs_page import LogsPage
from app.ui.placeholders import PlaceholderPage
from app.ui.chat_page import ChatPage
from app.ui.settings_page import SettingsPage
from app.ui.models_page import ModelsPage
from app.ui.agent_dashboard import AgentDashboardPage
from app.ui.wallet_page import WalletPage
import os
import sys

class MainWindow(QMainWindow):
    def __init__(self, hardware_info: dict, log_file_path: str, db_manager=None):
        super().__init__()
        self.hardware_info = hardware_info
        self.log_file_path = log_file_path
        self.db_manager = db_manager
        
        self.setWindowTitle("ZYRA")
        self.resize(1150, 650)
        
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
        
        # Sidebar Container
        sidebar_container = QWidget()
        sidebar_container.setFixedWidth(70)
        sidebar_layout = QVBoxLayout(sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        
        # Global Version Label
        from PySide6.QtWidgets import QLabel
        from PySide6.QtCore import Qt, QSize
        import json, os
        
        user_data_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ZYRA AI")
        current_version = "v1.0.82"
        current_v_path = os.path.join(user_data_dir, "current_version.json")
        if os.path.exists(current_v_path):
            try:
                with open(current_v_path, 'r') as f:
                    current_version = json.load(f).get("version", "v1.0.82")
            except:
                pass
                
        self.version_lbl = QLabel(current_version)
        self.version_lbl.setAlignment(Qt.AlignCenter)
        self.version_lbl.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 800; padding-top: 15px; padding-bottom: 10px;")
        sidebar_layout.addWidget(self.version_lbl)
        
        # Sidebar List
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setStyleSheet("border: none; background-color: transparent;")
        self.sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        sidebar_data = [
            ("dashboard.png", "Dashboard"),
            ("chat.png", "Chat"),
            ("models.png", "Models"),
            ("cpu.png", "Agent & Mining"),
            ("dataset.png", "Wallet"),
            ("settings.png", "Settings")
        ]
        
        from PySide6.QtWidgets import QListWidgetItem
        
        # Resolve assets dir safely across environments
        assets_dir = os.path.join(os.path.dirname(__file__), "assets", "icons")
        
        self.sidebar.setIconSize(QSize(28, 28))
        
        for icon_file, tooltip in sidebar_data:
            item = QListWidgetItem()
            icon_path = os.path.join(assets_dir, icon_file)
            if os.path.exists(icon_path):
                item.setIcon(QIcon(icon_path))
            else:
                item.setText("?") # Fallback if SVG missing
                
            item.setToolTip(tooltip)
            self.sidebar.addItem(item)
            
        sidebar_layout.addWidget(self.sidebar)
        
        # Pages Container
        self.pages = QStackedWidget()
        self.pages.setObjectName("PagesContainer")
        
        self.dashboard_page = DashboardPage(self.hardware_info)
        self.chat_page = ChatPage(db_manager=self.db_manager)
        self.models_page = ModelsPage(self.hardware_info, self.chat_page)
        self.agent_page = AgentDashboardPage()
        self.wallet_page = WalletPage()
        self.settings_page = SettingsPage(self.chat_page)
        # self.logs_page = LogsPage(self.log_file_path)
        
        self.pages.addWidget(self.dashboard_page)
        self.pages.addWidget(self.chat_page)
        self.pages.addWidget(self.models_page)
        self.pages.addWidget(self.agent_page)
        self.pages.addWidget(self.wallet_page)
        self.pages.addWidget(self.settings_page)
        # self.pages.addWidget(self.logs_page)
        
        self.sidebar.currentRowChanged.connect(self.pages.setCurrentIndex)
        
        main_layout.addWidget(sidebar_container)
        main_layout.addWidget(self.pages)
        
        # Instantiate Spotlight
        from app.ui.spotlight import SpotlightWidget
        self.spotlight = SpotlightWidget()
        self.spotlight.submitted.connect(self.handle_spotlight_query)
        
        # self.setup_system_tray(icon_path)
        self.setup_global_hotkey()
        self.setup_hot_reload()

    def handle_spotlight_query(self, query: str):
        self.show_and_activate()
        self.sidebar.setCurrentRow(1) # Switch to chat page
        self.chat_page.input_field.setText(query)
        self.chat_page.on_send_click()

    def setup_system_tray(self, icon_path):
        from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
        from PySide6.QtGui import QIcon
        
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(icon_path))
        
        # Create the context menu
        tray_menu = QMenu()
        
        show_action = tray_menu.addAction("Show ZYRA AI")
        show_action.triggered.connect(self.show_and_activate)
        
        quit_action = tray_menu.addAction("Quit")
        quit_action.triggered.connect(QApplication.instance().quit)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()
        
    def on_tray_activated(self, reason):
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.Trigger:
            self.show_and_activate()
            
    def show_and_activate(self):
        self.show()
        self.activateWindow()
        self.raise_()
        
    def closeEvent(self, event):
        event.accept()

    def setup_global_hotkey(self):
        from PySide6.QtCore import QThread, Signal
        import keyboard
        
        class HotkeyThread(QThread):
            hotkey_pressed = Signal()
            
            def run(self):
                # This will run blocking in the thread
                keyboard.add_hotkey('alt+space', self.on_hotkey)
                keyboard.wait()
                
            def on_hotkey(self):
                self.hotkey_pressed.emit()
                
        self.hotkey_thread = HotkeyThread(self)
        self.hotkey_thread.hotkey_pressed.connect(self.spotlight.show_and_focus)
        self.hotkey_thread.start()

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
                subprocess.Popen([exe_path])
            else:
                python_exe = sys.executable
                run_script = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "run.py")
                subprocess.Popen([python_exe, run_script])
            QApplication.instance().quit()

