import os
from pathlib import Path
from dotenv import load_dotenv
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DATA = Path(os.getenv("SPILL_DATA", str(ROOT / "runtime"))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
WORKSPACES = DATA / "workspaces"
WORKSPACES.mkdir(exist_ok=True)
JWT_SECRET = os.getenv("SPILL_JWT_SECRET", "")
ENCRYPTION_KEY = os.getenv("SPILL_ENCRYPTION_KEY", "")
if len(JWT_SECRET) < 32 or not ENCRYPTION_KEY:
    raise RuntimeError("Secrets missing. Run .\\.venv\\Scripts\\python scripts\\configure.py from SPILL.")
CIPHER = Fernet(ENCRYPTION_KEY.encode())
MODEL_PATH = Path(os.getenv("SPILL_MODEL", str(ROOT / "ml/checkpoints/graphsage.pt")))
CORS = os.getenv("SPILL_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

