import os
import tempfile
from pathlib import Path
from cryptography.fernet import Fernet
TEST_DATA=tempfile.TemporaryDirectory(prefix="spill-tests-")
os.environ["SPILL_DATA"]=TEST_DATA.name
os.environ["SPILL_JWT_SECRET"]="test-secret-"+("a"*48)
os.environ["SPILL_ENCRYPTION_KEY"]=Fernet.generate_key().decode()
os.environ["SPILL_MODEL"]=str(Path(__file__).resolve().parents[1]/"ml/checkpoints/graphsage.pt")

def pytest_sessionfinish(session,exitstatus):
    from backend.app.db import engine
    from backend.app.repositories import remove_workspace
    from backend.app.config import WORKSPACES
    engine.dispose()
    for workspace in WORKSPACES.iterdir():
        if workspace.is_dir():remove_workspace(workspace)
    TEST_DATA.cleanup()

