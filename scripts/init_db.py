import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.db import init_db
init_db()
print("SQLite schema initialized. Existing records preserved.")

