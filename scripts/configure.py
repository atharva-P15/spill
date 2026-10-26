from pathlib import Path
import secrets
from cryptography.fernet import Fernet
root=Path(__file__).resolve().parents[1]
env=root/".env"
if not env.exists():
    env.write_text("SPILL_JWT_SECRET="+secrets.token_urlsafe(48)+"\nSPILL_ENCRYPTION_KEY="+Fernet.generate_key().decode()+"\n",encoding="utf-8")
    print("Created local .env secrets. Keep this file private and back it up.")
else:
    print("Existing .env preserved.")

