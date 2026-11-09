"""工具注册表 - 装饰器注册 + 元数据收集（供 RAG 索引）"""

import inspect
from agents import function_tool

# SDK 工具对象: name -> FunctionTool
_tool_objects: dict[str, object] = {}
# 工具元数据（供向量库索引）: [{name, description, params}]
_tool_docs: list[dict] = []


def tool(func):
    """注册函数为 SDK 工具，同时收集元数据供 RAG 索引"""
    sig = inspect.signature(func)
    params = ", ".join(
        f"{name}: {param.annotation.__name__ if param.annotation is not inspect.Parameter.empty else 'Any'}"
        for name, param in sig.parameters.items()
    )
    _tool_docs.append({
        "name": func.__name__,
        "description": (func.__doc__ or "").strip(),
        "params": params,
    })
    t = function_tool(func)
    _tool_objects[func.__name__] = t
    return t


def get_tool_by_name(name: str):
    return _tool_objects.get(name)


def get_all_tools() -> list:
    """返回所有已注册的 SDK 工具对象（供 Agent 组装 tools=）"""
    return list(_tool_objects.values())


def get_all_tool_docs() -> list[dict]:
    return list(_tool_docs)


def get_all_tool_names() -> list[str]:
    return list(_tool_objects.keys())
