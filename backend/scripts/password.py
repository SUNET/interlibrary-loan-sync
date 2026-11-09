"""CLI for generating random secrets and Argon2 password hashes.

Usage:
    uv run python scripts/secrets.py generate --len 32
    uv run python scripts/secrets.py generate --hash --format alnum --len 24
    uv run python scripts/secrets.py generate --format urlsafe --len 32 --count 3
    uv run python scripts/secrets.py generate --format urlsafe --len 32 --count 3
    uv run python scripts/secrets.py hash "my-password"
    uv run python scripts/secrets.py verify "my-password" "$argon2id$..."
"""

from __future__ import annotations

import argparse
import getpass
import secrets as stdlib_secrets
import string
import sys
from typing import Literal

from pwdlib import PasswordHash

SecretFormat = Literal["hex", "urlsafe", "alnum"]

ALNUM_ALPHABET = string.ascii_letters + string.digits
_HASHER = PasswordHash.recommended()


def generate_random_secret(length: int = 32, fmt: SecretFormat = "hex") -> str:
    """Generate a cryptographically secure random secret."""
    if length < 1:
        raise ValueError("length must be >= 1")
    if fmt == "hex":
        return stdlib_secrets.token_hex(length)
    if fmt == "urlsafe":
        return stdlib_secrets.token_urlsafe(length)
    if fmt == "alnum":
        return "".join(stdlib_secrets.choice(ALNUM_ALPHABET) for _ in range(length))
    raise ValueError(f"Unsupported format: {fmt}")


def generate_argon2_hash_password(password: str, show: bool = False) -> str:
    """Generate an Argon2 hash for a given password."""
    hashed = _HASHER.hash(password)
    if show:
        print(f"Password: {password}")
        print(f"Hash:     {hashed}")
    return hashed


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against an Argon2 hash."""
    return _HASHER.verify(password, hashed)


def _cmd_generate(args: argparse.Namespace) -> int:
    for i in range(args.count):
        if i > 0 and args.hash:
            print("---")
        secret = generate_random_secret(length=args.length, fmt=args.format)
        if args.hash:
            generate_argon2_hash_password(secret, show=True)
        else:
            print(secret)
    return 0


def _cmd_hash(args: argparse.Namespace) -> int:
    password = args.password or getpass.getpass("Password: ")
    print(generate_argon2_hash_password(password, show=False))
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    password = args.password or getpass.getpass("Password: ")
    matched = verify_password(password, args.hashed)
    print("MATCH" if matched else "MISMATCH")
    return 0 if matched else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="secrets",
        description="Generate random secrets and Argon2 password hashes.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate random secret(s).")
    gen.add_argument(
        "-l",
        "--len",
        "--length",
        dest="length",
        type=int,
        default=32,
        help="Length / byte count for generated secret (default: 32).",
    )
    gen.add_argument(
        "-f",
        "--format",
        choices=("hex", "urlsafe", "alnum"),
        default="hex",
        help="Output encoding: hex, urlsafe, or alnum (default: hex).",
    )
    gen.add_argument(
        "--hash",
        action="store_true",
        help="Also compute and print the Argon2 hash of each generated secret.",
    )
    gen.add_argument(
        "-n",
        "--count",
        type=int,
        default=1,
        help="Number of secrets to generate (default: 1).",
    )
    gen.set_defaults(func=_cmd_generate)

    hsh = sub.add_parser("hash", help="Hash an existing password with Argon2.")
    hsh.add_argument(
        "password",
        nargs="?",
        help="Password to hash (prompts securely if omitted).",
    )
    hsh.set_defaults(func=_cmd_hash)

    ver = sub.add_parser("verify", help="Verify a password against an Argon2 hash.")
    ver.add_argument("hashed", help="Argon2 hash string to verify against.")
    ver.add_argument(
        "-p",
        "--password",
        help="Plaintext password (prompts securely if omitted).",
    )
    ver.set_defaults(func=_cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
