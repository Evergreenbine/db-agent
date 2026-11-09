"""数据库工具集 - 导入即触发 @tool 注册"""

from . import run_sql  # noqa: F401
from . import resolve_form  # noqa: F401
from . import search_schema  # noqa: F401
from . import get_table_detail  # noqa: F401
from . import list_modules  # noqa: F401
from . import execute_write  # noqa: F401
from app.agents.memory import knowledge  # noqa: F401  query_knowledge/save_knowledge
