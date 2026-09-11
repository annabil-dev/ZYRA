import pytest
import os
import sqlite3
import logging
from app.core.database import DatabaseManager

def test_database_initialization(tmp_path):
    logger = logging.getLogger("test")
    db_dir = str(tmp_path / "database")
    db_manager = DatabaseManager(db_dir, logger)
    
    # Check if file was created
    db_path = os.path.join(db_dir, "my_ai.sqlite")
    assert os.path.isfile(db_path)
    
    # Check if connection is alive and table exists
    cursor = db_manager.connection.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='metadata';")
    assert cursor.fetchone() is not None
    
    db_manager.close()
