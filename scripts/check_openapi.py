from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
FRONTEND_ROOT = REPOSITORY_ROOT / "frontend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app  # noqa: E402


def main() -> None:
    checked_openapi = FRONTEND_ROOT / "openapi.json"
    checked_schema = FRONTEND_ROOT / "src" / "api" / "generated" / "schema.ts"
    expected_openapi = json.dumps(app.openapi(), indent=2) + "\n"
    if checked_openapi.read_text(encoding="utf-8") != expected_openapi:
        raise SystemExit("OpenAPI snapshot is stale; run `make openapi`.")

    with tempfile.TemporaryDirectory(prefix="unsubscribe-openapi-") as temporary:
        generated_schema = Path(temporary) / "schema.ts"
        subprocess.run(
            [
                str(FRONTEND_ROOT / "node_modules" / ".bin" / "openapi-typescript"),
                str(checked_openapi),
                "-o",
                str(generated_schema),
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
        )
        if generated_schema.read_bytes() != checked_schema.read_bytes():
            raise SystemExit("Generated TypeScript client is stale; run `make openapi`.")
    print("OpenAPI snapshot and generated TypeScript client are current.")


if __name__ == "__main__":
    main()
