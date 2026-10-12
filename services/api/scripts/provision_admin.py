"""Provision SAULI's dedicated Supabase Auth administrator account.

Run from services/api. The password is read from the terminal and never saved.
"""

from getpass import getpass
from pathlib import Path

from supabase import create_client

from app.config import Settings


ADMIN_USERNAME = "sauli-admin"
ADMIN_EMAIL = "sauli-admin@sauli.example"
ROOT = Path(__file__).resolve().parents[3]


def all_users(client):
    page = 1
    while True:
        users = client.auth.admin.list_users(page=page, per_page=200)
        yield from users
        if len(users) < 200:
            return
        page += 1


def set_local_env(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    replacement = f"{key}={value}"
    lines = [replacement if line.startswith(f"{key}=") else line for line in lines]
    if not any(line.startswith(f"{key}=") for line in lines):
        lines.append(replacement)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    settings = Settings.from_env()
    if not settings.supabase_url or not settings.supabase_service_role_key or not settings.supabase_publishable_key:
        raise SystemExit("Supabase URL, service role key, and publishable key are required in services/.env")

    password = getpass("Password for sauli-admin: ")
    if len(password) < 12:
        raise SystemExit("Admin password must have at least 12 characters")

    admin_client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    users = list(all_users(admin_client))
    matches = [user for user in users if (user.email or "").lower() == ADMIN_EMAIL]
    if len(matches) > 1:
        raise SystemExit("Multiple accounts use the admin email; no changes made")

    metadata = {"sauli_role": "admin", "sauli_admin_username": ADMIN_USERNAME}
    if matches:
        user = matches[0]
        metadata = {**user.app_metadata, **metadata}
        admin_client.auth.admin.update_user_by_id(user.id, {"password": password, "app_metadata": metadata, "email_confirm": True})
        admin_id = user.id
    else:
        response = admin_client.auth.admin.create_user({
            "email": ADMIN_EMAIL,
            "password": password,
            "email_confirm": True,
            "app_metadata": metadata,
            "user_metadata": {"username": ADMIN_USERNAME},
        })
        admin_id = response.user.id

    # Revoke any older SAULI admin grants; the API also pins the admin ID.
    for user in users:
        if user.id == admin_id:
            continue
        old_metadata = user.app_metadata or {}
        if old_metadata.get("sauli_role") == "admin" or old_metadata.get("role") == "admin":
            updated = {**old_metadata}
            updated.pop("sauli_role", None)
            updated.pop("sauli_admin_username", None)
            if updated.get("role") == "admin":
                updated["role"] = "authenticated"
            admin_client.auth.admin.update_user_by_id(user.id, {"app_metadata": updated})

    auth_client = create_client(settings.supabase_url, settings.supabase_publishable_key)
    result = auth_client.auth.sign_in_with_password({"email": ADMIN_EMAIL, "password": password})
    if result.user.id != admin_id or result.user.app_metadata.get("sauli_role") != "admin":
        raise SystemExit("Admin sign-in verification failed; local configuration was not changed")

    set_local_env(ROOT / "services" / ".env", "SAULI_ADMIN_USER_ID", admin_id)
    set_local_env(ROOT / "frontend" / ".env", "SAULI_ADMIN_USER_ID", admin_id)
    print(f"Admin account verified. User ID: {admin_id}")
    print("Local API and frontend admin IDs updated. Restart both servers.")


if __name__ == "__main__":
    main()
