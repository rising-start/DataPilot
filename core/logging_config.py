"""统一日志配置（基础日志，避免散落的 logger 没有 handler 而“静默”）。

用法：在进程入口（server/main.py、eval_runner 等）import 后调用 setup_logging()。
仅配置一次：logging.basicConfig 在已有 handler 时不会重复生效，重复调用安全。

可通过环境变量控制：
  LOG_LEVEL  日志级别，默认 INFO（DEBUG/INFO/WARNING/ERROR）
  LOG_FILE   可选的日志文件路径；设置后将同时写文件（按大小滚动，保留 5 份）
"""
import logging
import os
from logging.handlers import RotatingFileHandler


def _log_level() -> int:
    raw = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    return getattr(logging, raw, logging.INFO)


def setup_logging() -> None:
    level = _log_level()
    fmt = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = []

    log_file = os.getenv("LOG_FILE")
    if log_file:
        
        fh = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
        fh.setFormatter(logging.Formatter(fmt, datefmt))
        handlers.append(fh)

    
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter(fmt, datefmt))
    handlers.append(sh)

    logging.basicConfig(level=level, handlers=handlers, datefmt=datefmt, force=True)
