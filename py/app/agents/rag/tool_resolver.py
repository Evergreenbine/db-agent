"""工具检索器 - 用户输入 → 向量检索 → 动态工具列表（支持 module 过滤）"""

from app.agents.rag.store import retrieve
from app.agents.tools.registry import get_tool_by_name


async def resolve_tools(user_input: str, top_k: int = 5, module: str | None = None) -> list:
    """根据用户输入检索相关工具，返回 SDK 工具对象列表。

    module: 指定时只检索该模块的工具（对应 SKILL.md 的 module 字段）。
    """
    names = retrieve(user_input, top_k=top_k, module=module)
    tools = [get_tool_by_name(n) for n in names]
    return [t for t in tools if t is not None]
