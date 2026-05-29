import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'solar.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    schema = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'schema.sql')
    conn = get_db()
    with open(schema) as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
