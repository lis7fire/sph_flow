from __future__ import annotations

import logging
from pathlib import Path

from sph_flow.logging_config import configure_logging
from sph_flow.server import MonitorHttpServer
from sph_flow.service import CaptureScheduler, MonitorService

logger = logging.getLogger(__name__)


def run() -> None:
    root_dir = Path(__file__).resolve().parents[2]
    log_path = configure_logging(root_dir)
    logger.info("应用启动 root_dir=%s log_path=%s", root_dir, log_path)
    service = MonitorService(root_dir)
    scheduler = CaptureScheduler(service)
    scheduler.start()
    server = MonitorHttpServer(service, scheduler, root_dir / "src" / "sph_flow" / "web")
    print(f"日志文件：{log_path}")
    server.serve_forever()
