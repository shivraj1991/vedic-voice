"""Simulated Clerk tokens for local development and tests (never used in prod).

    uv run python -m vv_backend.devtools init                 # writes .dev-keys/ (gitignored)
    uv run python -m vv_backend.devtools token --role advisor --sub user_dev_advisor
    pbpaste | uv run python -m vv_backend.devtools verify   # check a real Clerk token

Run the API against the generated JWKS with:
    VV_ENV=dev VV_DEV_JWKS_PATH=.dev-keys/jwks.json CLERK_ISSUER=https://dev.clerk.local \\
    CLERK_AUTHORIZED_PARTIES=http://localhost:8081 DATABASE_URL=... \\
    uv run uvicorn --factory vv_backend.api.app:create_app
Settings refuse VV_DEV_JWKS_PATH when VV_ENV=prod.
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

DEV_ISSUER = "https://dev.clerk.local"
DEV_AZP = "http://localhost:8081"
DEV_DIR = Path(".dev-keys")


def new_keypair(kid: str | None = None) -> tuple[rsa.RSAPrivateKey, dict]:
    """RSA key + matching JWKS document (same shape as Clerk's /.well-known/jwks.json)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": kid or uuid.uuid4().hex[:16], "use": "sig", "alg": "RS256"})
    return key, {"keys": [jwk]}


def make_token(
    key: rsa.RSAPrivateKey,
    kid: str,
    *,
    sub: str = "user_dev",
    role: str | None = None,
    issuer: str = DEV_ISSUER,
    azp: str | None = DEV_AZP,
    ttl_s: int = 3600,
    now: float | None = None,
) -> str:
    now = time.time() if now is None else now
    claims = {"sub": sub, "iss": issuer, "azp": azp, "iat": int(now), "nbf": int(now) - 5,
              "exp": int(now) + ttl_s, "sid": "sess_dev"}  # fmt: skip
    if role:
        claims["role"] = role
    if azp is None:
        claims.pop("azp")
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


def verify_from_stdin() -> None:
    """Check a real Clerk session token (paste from the app/browser) against CLERK_* env vars.

    Prints the claims we rely on, then verifies signature/iss/azp/exp like the API does.
    """
    import sys

    from .api.auth import ClerkJWKS, verify_token
    from .api.settings import Settings

    settings = Settings.from_env()
    token = sys.stdin.read().strip()
    claims = jwt.decode(token, options={"verify_signature": False})
    print("claims:", {k: claims.get(k) for k in ("iss", "azp", "sub", "role", "exp")})
    print("verified:", verify_token(token, settings, ClerkJWKS(settings.clerk_jwks_url)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    t = sub.add_parser("token")
    t.add_argument("--sub", default="user_dev")
    t.add_argument("--role", choices=["admin", "advisor", "learner"], default=None)
    t.add_argument("--ttl", type=int, default=3600)
    sub.add_parser("verify", help="verify a real Clerk token from stdin against CLERK_* env vars")
    args = ap.parse_args()
    if args.cmd == "verify":
        verify_from_stdin()
        return
    if args.cmd == "init":
        key, jwks = new_keypair()
        DEV_DIR.mkdir(exist_ok=True)
        (DEV_DIR / "jwks.json").write_text(json.dumps(jwks, indent=1))
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())  # fmt: skip
        (DEV_DIR / "private.pem").write_bytes(pem)
        print(f"wrote {DEV_DIR}/jwks.json and private.pem (dev only, gitignored)")
        return
    key = serialization.load_pem_private_key((DEV_DIR / "private.pem").read_bytes(), None)
    kid = json.loads((DEV_DIR / "jwks.json").read_text())["keys"][0]["kid"]
    print(make_token(key, kid, sub=args.sub, role=args.role, ttl_s=args.ttl))


if __name__ == "__main__":
    main()
