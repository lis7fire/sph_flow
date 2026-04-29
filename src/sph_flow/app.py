from __future__ import annotations

from pathlib import Path

from sph_flow.server import MonitorHttpServer
from sph_flow.service import CaptureScheduler, MonitorService


def run() -> None:
    root_dir = Path(__file__).resolve().parents[2]
    service = MonitorService(root_dir)
    scheduler = CaptureScheduler(service)
    scheduler.start()
    server = MonitorHttpServer(service, scheduler, root_dir / "src" / "sph_flow" / "web")
    server.serve_forever()
