"""配置应用日志格式，记录运行状态并避免输出凭据及服务商错误正文。"""

import logging


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
