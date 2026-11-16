from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipesor_rag_retrieval.api import create_app
from pipesor_rag_retrieval.configuration import Settings


DEFAULT_OUTPUT = Path("docs/openapi/internal-v1.json")


def rendered_schema() -> str:
    contract_settings = Settings(
        authentication_mode="entra",
        runtime_environment="dev",
        entra_tenant_id="11111111-1111-4111-8111-111111111111",
        entra_audience="22222222-2222-4222-8222-222222222222",
        entra_recommendation_client_id="33333333-3333-4333-8333-333333333333",
    )
    return json.dumps(create_app(settings=contract_settings).openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or verify the internal OpenAPI contract.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = rendered_schema()
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != expected:
            print(f"OpenAPI contract is stale: {args.output}")
            return 1
        print(f"OpenAPI contract is current: {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(expected, encoding="utf-8", newline="\n")
    print(f"OpenAPI contract exported: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
