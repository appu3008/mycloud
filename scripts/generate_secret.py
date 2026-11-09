#!/usr/bin/env python3
"""Generate a strong secret and print the .env line for MYCLOUD_SECRET_KEY.

Never hardcode or commit the generated value. Usage:
    python3 scripts/generate_secret.py
"""

import secrets


def main() -> None:
    key = secrets.token_urlsafe(48)
    print("Add this line to your project-root .env (never commit .env):")
    print(f"MYCLOUD_SECRET_KEY={key}")


if __name__ == "__main__":
    main()
