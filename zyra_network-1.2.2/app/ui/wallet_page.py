from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
                               QLineEdit, QPushButton, QMessageBox)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
import os
import datetime
import requests
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
        
        # Start Price Ticker Timer
        self.price_timer = QTimer(self)
        self.price_timer.timeout.connect(self.fetch_live_price)
        self.price_timer.start(3000) # Every 3 seconds
        
        # Initial fetch
        self.fetch_live_price()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(20)

        # Title Area
        title_layout = QHBoxLayout()
        title = QLabel("ZYRA Wallet")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #ffffff;")
        
        self.lbl_live_price = QLabel("ZYRA Price: Loading...")
        self.lbl_live_price.setStyleSheet("font-size: 16px; font-weight: bold; color: #10b981; background: #064e3b; padding: 5px 10px; border-radius: 5px;")
        
        title_layout.addWidget(title)
        title_layout.addStretch()
        title_layout.addWidget(self.lbl_live_price)
        main_layout.addLayout(title_layout)

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
        
        self.lbl_usd_balance = QLabel("≈ $0.00 USD")
        self.lbl_usd_balance.setStyleSheet("font-size: 18px; color: #93c5fd; font-weight: 600;")
        card_layout.addWidget(self.lbl_usd_balance)
        
        lbl_address = QLabel(f"Address: {self.wallet.address}")
        lbl_address.setStyleSheet("font-size: 12px; margin-top: 15px; color: #e0e7ff; font-family: monospace;")
        lbl_address.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card_layout.addWidget(lbl_address)
        
        main_layout.addWidget(card_frame)
        
        # Withdraw Section
        withdraw_layout = QHBoxLayout()
        self.metamask_input = QLineEdit()
        self.metamask_input.setPlaceholderText("Enter MetaMask Address (0x...)")
        self.metamask_input.setStyleSheet("padding: 10px; border-radius: 5px; background: #1e293b; color: white;")
        
        self.btn_withdraw = QPushButton("Withdraw to MetaMask")
        self.btn_withdraw.setStyleSheet("padding: 10px 20px; border-radius: 5px; background: #4f46e5; color: white; font-weight: bold;")
        self.btn_withdraw.clicked.connect(self.handle_withdraw)
        
        withdraw_layout.addWidget(self.metamask_input)
        withdraw_layout.addWidget(self.btn_withdraw)
        main_layout.addLayout(withdraw_layout)

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
            if tx['type'] == 'MINT':
                type_item.setForeground(Qt.green)
            elif tx['type'] == 'WITHDRAW':
                type_item.setForeground(Qt.red)
            else:
                type_item.setForeground(Qt.white)
            self.tx_table.setItem(i, 1, type_item)
            
            if tx['type'] == 'MINT':
                amount_str = f"+{tx['amount']}"
            elif tx['type'] == 'WITHDRAW':
                amount_str = f"-{tx['amount']}"
            else:
                amount_str = str(tx['amount'])
            self.tx_table.setItem(i, 2, QTableWidgetItem(amount_str))
            
            txid_item = QTableWidgetItem(tx['txid'])
            self.tx_table.setItem(i, 3, txid_item)
            
        self.tx_table.resizeColumnsToContents()
        self.tx_table.horizontalHeader().setStretchLastSection(True)
            
    def refresh_data(self):
        """Called to update the UI when new blocks are mined."""
        balance = self.ledger.get_balance(self.wallet.address)
        self.lbl_balance.setText(f"{balance:.4f} ZYRA")
        self.populate_transactions()
        self.fetch_live_price()
        
    def fetch_live_price(self):
        try:
            response = requests.get("http://127.0.0.1:5000/price", timeout=2)
            if response.status_code == 200:
                data = response.json()
                price = data.get("price_usd", 0.0)
                change = data.get("change_24h", 0.0)
                
                # Update Ticker
                color = "#10b981" if change >= 0 else "#ef4444"
                bg_color = "#064e3b" if change >= 0 else "#7f1d1d"
                indicator = "🟢" if change >= 0 else "🔴"
                
                self.lbl_live_price.setText(f"Live Price: ${price:.4f} {indicator} {change:+.2f}%")
                self.lbl_live_price.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {color}; background: {bg_color}; padding: 5px 10px; border-radius: 5px;")
                
                # Update USD Balance
                balance = self.ledger.get_balance(self.wallet.address)
                usd_value = balance * price
                self.lbl_usd_balance.setText(f"≈ ${usd_value:.2f} USD")
        except Exception:
            self.lbl_live_price.setText("Live Price: Disconnected")
            self.lbl_live_price.setStyleSheet("font-size: 16px; font-weight: bold; color: #94a3b8; background: #334155; padding: 5px 10px; border-radius: 5px;")
        
    def handle_withdraw(self):
        address = self.metamask_input.text().strip()
        if not address.startswith("0x") or len(address) != 42:
            QMessageBox.warning(self, "Invalid Address", "Please enter a valid MetaMask address (0x...).")
            return
            
        balance = self.ledger.get_balance(self.wallet.address)
        if balance <= 0:
            QMessageBox.warning(self, "Insufficient Balance", "You have no ZYRA to withdraw.")
            return
            
        import requests
        try:
            self.btn_withdraw.setEnabled(False)
            self.btn_withdraw.setText("Processing...")
            
            payload = {
                "metamask_address": address,
                "amount": balance,
                "local_wallet": self.wallet.address
            }
            
            # Send to Bridge Server (running locally for testing)
            response = requests.post("http://127.0.0.1:5000/withdraw", json=payload)
            data = response.json()
            
            if response.status_code == 200:
                # Update local ledger to deduct balance (add a negative transaction)
                self.ledger.add_withdraw_transaction(self.wallet.address, balance, data.get("tx_hash", ""))
                self.refresh_data()
                QMessageBox.information(self, "Success", f"Withdrawal successful!\nTX Hash: {data.get('tx_hash')}")
                self.metamask_input.clear()
            else:
                QMessageBox.warning(self, "Error", f"Withdrawal failed: {data.get('error')}")
                
        except Exception as e:
            QMessageBox.critical(self, "Network Error", f"Could not connect to Bridge Server.\nEnsure the server is running on port 5000.\nError: {e}")
        finally:
            self.btn_withdraw.setEnabled(True)
            self.btn_withdraw.setText("Withdraw to MetaMask")

