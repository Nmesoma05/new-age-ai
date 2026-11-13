"""Write docs/openapi.json from the application. Needs no database or real secrets."""
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from cryptography.fernet import Fernet  # noqa: E402

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("JWT_SECRET", "export-only-" + "x" * 32)
os.environ.setdefault("CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("FILE_SCANNER", "disabled_dev_only")
os.environ["ENV"] = "dev"

from app.main import create_app  # noqa: E402

out = pathlib.Path(__file__).resolve().parents[1] / "docs" / "openapi.json"
out.write_text(json.dumps(create_app().openapi(), indent=2))
print(f"wrote {out}")
