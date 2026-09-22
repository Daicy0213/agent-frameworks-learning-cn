"""Google ADK 评估教学项目。

ADK CLI 会从本包的 ``agent`` 模块中查找 ``root_agent``。
"""

from .agent import root_agent

__all__ = ["root_agent"]
