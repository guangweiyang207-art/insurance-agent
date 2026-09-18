from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any
import structlog

def configure_logging(
    *,
    level: str = "INFO",
    log_format: str = "console",
    log_file: str | None = None,        # 新增：日志文件路径，为 None 则不输出到文件
) -> None:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,                # 合并上下文变量
        structlog.stdlib.add_logger_name,                       # 添加日志器名称
        structlog.stdlib.add_log_level,                         # 添加日志级别
        structlog.processors.TimeStamper(fmt="iso", utc=True),  # 添加 ISO 时间戳（UTC）
        structlog.processors.StackInfoRenderer(),               # 渲染堆栈信息
        structlog.processors.format_exc_info,                   # 格式化异常信息
    ]
    # 根据格式选择 JSON 或控制台输出
    if log_format.lower() == "json":
        processors.append(structlog.processors.JSONRenderer(ensure_ascii=False))
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(_log_level(level))

    # 清除已有处理器，避免重复
    root_logger.handlers.clear()

    # 控制台处理器（固定输出到 stdout）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(console_handler)

    # 文件处理器（可选）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(file_handler)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 手动控制sqlalchemy的日志级别
    logging.getLogger("sqlalchemy.engine").setLevel(root_logger.level)

def get_logger(name: str):
    """获取指定名称的 structlog 日志器"""
    return structlog.get_logger(name)


def _log_level(level: str) -> int:
    """将日志级别字符串转换为 logging 模块的整数常量"""
    return getattr(logging, level.upper(), logging.INFO)
