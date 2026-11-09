"""数据源管理路由"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.datasource import registry
from app.datasource.adapter import supported_types

router = APIRouter(prefix="/api/datasource", tags=["datasource"])


class DataSourceCreate(BaseModel):
    name: str = Field(..., description="数据源名称，如 oa / hr")
    db_type: str = Field(..., description="oracle / sqlserver / mysql")
    host: str = Field(..., description="主机地址")
    port: int = Field(..., description="端口")
    database_name: str = Field(..., description="Oracle: SID; SQLServer/MySQL: 库名")
    username: str = Field(...)
    password: str = Field(...)
    description: str = Field("", description="描述")


@router.get("")
async def list_datasources():
    """列出全部数据源。"""
    return {"datasources": registry.list_all()}


@router.get("/types")
async def list_types():
    """列出支持的数据库类型。"""
    return {"types": supported_types()}


@router.post("")
async def create_datasource(req: DataSourceCreate):
    """新增数据源。"""
    result = registry.create(req.model_dump())
    return result


@router.delete("/{ds_id}")
async def delete_datasource(ds_id: int):
    """删除数据源。"""
    ok = registry.delete(ds_id)
    return {"deleted": ok}


@router.post("/{ds_id}/test")
async def test_datasource(ds_id: int):
    """测试连接。"""
    adapter = registry.get_adapter_by_id(ds_id)
    if not adapter:
        return {"ok": False, "message": "数据源不存在"}
    return adapter.test_connection()


@router.post("/{ds_id}/discover")
async def discover_tables(ds_id: int, include_backups: bool = False):
    """发现表（枚举全部表 + 行数），默认排除备份/临时表。"""
    adapter = registry.get_adapter_by_id(ds_id)
    if not adapter:
        return {"error": "数据源不存在"}
    tables = adapter.list_tables(include_backups=include_backups)
    return {
        "total": len(tables),
        "tables": tables[:200],
        "truncated": len(tables) > 200,
        "tables_count_total": len(tables),
    }


@router.get("/{ds_id}/tables/{table_name}/columns")
async def get_columns(ds_id: int, table_name: str):
    """获取某表的列信息。"""
    adapter = registry.get_adapter_by_id(ds_id)
    if not adapter:
        return {"error": "数据源不存在"}
    cols = adapter.get_columns(table_name)
    return {"table": table_name, "columns": cols, "count": len(cols)}
