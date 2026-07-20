#!/usr/bin/env python
"""Dump the FastAPI OpenAPI spec to a JSON file for frontend type generation.

Proof of concept — quota slice only. Rather than building the full application
(``create_app()`` runs DB migrations and seeds the default admin, which we don't
want as a build-time side effect), this constructs a bare FastAPI app and mounts
only the routers we want typed. To expand coverage, add more routers below or
switch to ``from mlflow_oidc_auth.routers import get_all_routers``.

Usage:
    python scripts/dump_openapi.py [output_path]

Defaults to writing ``openapi.json`` at the repository root.
"""

import json
import sys
from pathlib import Path

from fastapi import FastAPI

from mlflow_oidc_auth.routers.quota import ownership_router, quota_router

REPO_ROOT = Path(__file__).resolve().parent.parent


def build_spec() -> dict:
    app = FastAPI(
        title="MLflow OIDC Auth API",
        description="Generated OpenAPI spec (proof-of-concept: quota slice).",
        version="0.0.0",
    )
    # Slice under test. Expand this list (or use get_all_routers()) to grow coverage.
    app.include_router(quota_router)
    app.include_router(ownership_router)
    return app.openapi()


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "openapi.json"
    spec = build_spec()
    output.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"Wrote {output} ({len(spec.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()