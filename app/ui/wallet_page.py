from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QFrame)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
import os
import datetime
from ai.blockchain.wallet import ZyraWallet
from ai.blockchain.ledger import ZyraLedger

class WalletPage(QWidget):
    """
    A UI page to display the user's ZYRA Token Wallet, Balance, and Transactions.
    """
    def __init__(self):
        super().__init__()
        self.setObjectName("WalletPage")
        
        # Initialize Crypto Components
        user_data_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ZYRA AI")
        self.wallet = ZyraWallet(user_data_dir)
        self.ledger = ZyraLedger(user_data_dir)
        
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(20)

        # Title
        title = QLabel("ZYRA Wallet")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #ffffff;")
        main_layout.addWidget(title)

        # Balance Card
        card_frame = QFrame()
        card_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4f46e5, stop:1 #3b82f6);
                border-radius: 15px;
            }
            QLabel {
                background: transparent;
                color: white;
            }
        """)
        card_layout = QVBoxLayout(card_frame)
        card_layout.setContentsMargins(25, 25, 25, 25)
        
        lbl_bal_title = QLabel("Total Balance")
        lbl_bal_title.setStyleSheet("font-size: 14px; font-weight: 500; opacity: 0.8;")
        card_layout.addWidget(lbl_bal_title)
        
        # Fetch Balance
        balance = self.ledger.get_balance(self.wallet.address)
        
        self.lbl_balance = QLabel(f"{balance:.4f} ZYRA")
        self.lbl_balance.setStyleSheet("font-size: 36px; font-weight: 900; margin-top: 5px;")
        card_layout.addWidget(self.lbl_balance)
        
        lbl_address = QLabel(f"Address: {self.wallet.address}")
        lbl_address.setStyleSheet("font-size: 12px; margin-top: 15px; color: #e0e7ff; font-family: monospace;")
        lbl_address.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card_layout.addWidget(lbl_address)
        
        main_layout.addWidget(card_frame)

        # Transaction History
        lbl_history = QLabel("Recent Transactions (PoUW Mining)")
        lbl_history.setStyleSheet("font-size: 18px; font-weight: bold; color: #e2e8f0; margin-top: 20px;")
        main_layout.addWidget(lbl_history)

        self.tx_table = QTableWidget()
        self.tx_table.setColumnCount(4)
        self.tx_table.setHorizontalHeaderLabels(["Date", "Type", "Amount", "TXID"])
        self.tx_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tx_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.tx_table.setColumnWidth(3, 200)
        
        self.tx_table.setStyleSheet("""
            QTableWidget {
                background-color: #0f172a;
                color: #cbd5e1;
                border: 1px solid #1e293b;
                border-radius: 8px;
                gridline-color: #1e293b;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: white;
                font-weight: bold;
                border: none;
                padding: 5px;
            }
        """)
        
        self.populate_transactions()
        main_layout.addWidget(self.tx_table)

    def populate_transactions(self):
        txs = self.ledger.get_recent_transactions(20)
        self.tx_table.setRowCount(len(txs))
        
        for i, tx in enumerate(txs):
            dt = datetime.datetime.fromtimestamp(tx['timestamp']).strftime('%Y-%m-%d %H:%M')
            
            self.tx_table.setItem(i, 0, QTableWidgetItem(dt))
            
            type_item = QTableWidgetItem(tx['type'])
            type_item.setForeground(Qt.green if tx['type'] == 'MINT' else Qt.white)
            self.tx_table.setItem(i, 1, type_item)
            
            amount_str = f"+{tx['amount']}" if tx['type'] == 'MINT' else str(tx['amount'])
            self.tx_table.setItem(i, 2, QTableWidgetItem(amount_str))
            
            txid_item = QTableWidgetItem(tx['txid'])
            txid_item.setFont(QFont("Consolas", 9))
            self.tx_table.setItem(i, 3, txid_item)
            
    def refresh_data(self):
        """Called to update the UI when new blocks are mined."""
        balance = self.ledger.get_balance(self.wallet.address)
        self.lbl_balance.setText(f"{balance:.4f} ZYRA")
        self.populate_transactions()
