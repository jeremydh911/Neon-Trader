#!/usr/bin/env python3
"""Health / readiness check for self-hosted AhanaFlow (exit 0 = healthy)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.services.ahanaflow_vector_client import AhanaFlowVectorClient
    from app.services.ahanaflow_tls import tls_enabled

    host = os.getenv("AHANAFLOW_HOST", "127.0.0.1")
    port = int(os.getenv("AHANAFLOW_PORT", "9634"))
    client = AhanaFlowVectorClient(
        host=host,
        port=port,
        api_key=os.getenv("AHANAFLOW_API_KEY"),
        retries=int(os.getenv("AHANAFLOW_RETRIES", "2")),
        connect_eager=False,
        use_tls=tls_enabled() or None,
    )
    report = client.health()
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
