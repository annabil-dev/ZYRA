import sqlite3
import os
import logging

class DatabaseManager:
    """Manages SQLite database connection and initialization."""
    def __init__(self, db_dir: str, logger: logging.Logger):
        self.db_dir = db_dir
        self.logger = logger
        self.db_path = os.path.join(self.db_dir, "my_ai.sqlite")
        self.connection = None
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Connects to the database and creates initial tables if they don't exist."""
        try:
            os.makedirs(self.db_dir, exist_ok=True)
            self.connection = sqlite3.connect(self.db_path)
            self.logger.info(f"Connected to local database at {self.db_path}")
            
            cursor = self.connection.cursor()
            # Basic migration / table creation for future use
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL DEFAULT 'New Chat',
                    model_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tokens_per_sec REAL DEFAULT 0,
                    latency_ms REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
                )
            ''')
            self.connection.commit()
            self.logger.info("Database initialization successful.")
        except sqlite3.Error as e:
            self.logger.error(f"Failed to initialize database: {e}")
            if self.connection:
                self.connection.close()
                self.connection = None

    def close(self) -> None:
        """Closes the database connection safely."""
        if self.connection:
            self.connection.close()
            self.logger.info("Database connection closed.")
