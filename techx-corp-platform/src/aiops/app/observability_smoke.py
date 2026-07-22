from __future__ import annotations

import asyncio
import json

from .config import Settings
from .telemetry import TelemetryClient


async def run() -> int:
    telemetry = TelemetryClient(Settings())
    try:
        result = await telemetry.probe()
    finally:
        await telemetry.close()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if all(source["available"] for source in result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
