import pytest
import os
import sqlite3
import logging
import sys
from pathlib import Path

# These tests cover the archived desktop app, not the active ZYRA CLI package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "archives" / "legacy_app"))
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
