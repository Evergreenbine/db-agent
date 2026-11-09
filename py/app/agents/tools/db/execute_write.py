"""execute_write - 数据变更预览（不执行）。真正执行由用户在确认卡片点击后调用 /api/agent/confirm-write。

安全: 本工具只做 dry-run 预览，永远不执行 DML。
DELETE/UPDATE 必须带 WHERE；预览返回受影响数据供用户确认。
支持一条或多条语句组合预览（跨库/连表变更一张组合卡确认）。
"""

import json

from app.agents.tools.registry import tool
from app.agents.tools.db._write import build_combined_preview


@tool
def execute_write(purpose: str, steps: list) -> str:
    """对一条或多条 DELETE/UPDATE/INSERT/MERGE 语句做组合变更预览（不执行），返回受影响数据供用户在确认卡片一次确认。

    purpose: 【必填】用一句中文写明本次变更的目的——要改什么/为什么改，例如"把何春梅9月加班记录推送到人事库"。
    steps: 【必填】结构化步骤数组，每步是一个对象：
      {
        "sql": "UPDATE formtable_main_238 SET sylx2 = '调休' WHERE id = 123",  // 必填：最终执行的 DML
        "preview_sql": "SELECT id, sylx2 FROM formtable_main_238 WHERE id = 123",  // DELETE/UPDATE 必填：预览 SELECT
        "table": "FORMTABLE_MAIN_238",     // 必填：目标物理表名
        "table_label": "检测委托单明细1",  // 可选：表中文名，显示在步骤头
        "columns": ["sylx2"],              // 可选：受影响的列名；多表 JOIN 预览时传 [{"name":"col","table":"TABLE_A"}] 标注归属
        "datasource": "hr",                // 可选：数据源名；空/"oa" 默认 OA 库
        "column_labels": {"sybz": "审批意见", "id": "主键ID"},  // 可选：列名→中文名映射
        "column_meta": [                                    // 可选：列元数据，标注每列归属和角色
          {"name": "id", "table": "FORMTABLE_MAIN_238", "label": "主键"},
          {"name": "sylx2", "table": "FORMTABLE_MAIN_238", "label": "试验类型", "affected": true},
          {"name": "sylx1", "table": "FORMTABLE_MAIN_238_DT1", "label": "试验类型"}
        ]
        "description": "把请假类型改为调休"  // 可选：本步说明
      }
    何时用：用户明确要求新增/修改/删除数据时（单表或多表/跨库都一次调用本工具）。只读查询仍用 run_sql。
    重要规则：
      - 一步能做完的 SQL 不要拆分！直接写一条完整 DML（含 MERGE INTO、连表 UPDATE、子查询 SET 等复杂语句）。
      - preview_sql 是你自己写的 SELECT，用于让用户看到即将受影响的数据；它和 sql 的 WHERE 条件必须一致。
      - columns 是你知道的会被修改的列名，用于预览表格高亮；不确定就留空数组。
    安全：
      - 本工具只预览、不执行；执行需用户在组合确认卡片点「确定执行」。
      - DELETE/UPDATE 必须带 WHERE，否则拒绝。
      - 多步执行按序进行，任一步失败即停；已成功步骤无法自动回滚（跨库无分布式事务）。
    返回：JSON 字符串：
      {"requires_confirm":true,"step_count":N,"steps":[
        {"action":"delete|update|insert|merge","table":"...","sql":"...","preview_sql":"...",
         "columns":[...],"description":"...","datasource":"...",
         "preview":{"columns":[...],"rows":[[...]],"count":N,"truncated":bool}}
      ]}
      失败 {"error":"...","detail":"..."}。
    收到 requires_confirm=true 后：停止工具调用，用一句话告诉用户预览了几步、请在组合卡片确认后执行，然后结束回答；不要重复调用本工具。
    """
    result = build_combined_preview(steps)
    return json.dumps(result, ensure_ascii=False, default=str)
