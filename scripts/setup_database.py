"""Create project-local DB credentials without displaying or replacing existing secrets."""

import re
import secrets
from urllib.parse import quote

from dotenv import dotenv_values

from app.core.config import PROJECT_ROOT


def main() -> None:
    path = PROJECT_ROOT / ".env"
    text = path.read_text(encoding="utf-8")
    values = dotenv_values(path)
    updates = {}
    password = values.get("POSTGRES_PASSWORD") or secrets.token_urlsafe(32)
    if not values.get("POSTGRES_PASSWORD"):
        updates["POSTGRES_PASSWORD"] = password
    if not values.get("DATABASE_URL"):
        user = quote(values.get("POSTGRES_USER") or "matpilot", safe="")
        db = quote(values.get("POSTGRES_DB") or "matpilot", safe="")
        port = values.get("POSTGRES_PORT") or "5433"
        if not port.isdigit():
            raise ValueError("invalid database port")
        updates["DATABASE_URL"] = (
            f"postgresql+psycopg://{user}:{quote(password, safe='')}@127.0.0.1:{port}/{db}"
        )
    for name, value in updates.items():
        pattern = rf"(?m)^{name}=.*$"
        if re.search(pattern, text):
            text = re.sub(pattern, lambda _, name=name, value=value: f"{name}={value}", text)
        else:
            text += f"\n{name}={value}\n"
    if updates:
        path.write_text(text, encoding="utf-8")
    print("Project database configuration ready; credentials were not displayed.")


if __name__ == "__main__":
    main()
