"""resolve_form - 按业务名称解析 e-cology 自定义流程表单的物理表与字段"""

import json
import re

from pypinyin import lazy_pinyin, Style

from app.agents.tools.registry import tool
from app.agents.tools.db._query import LABEL_LANG_CN, execute_select, resolve_labels

_MAIN_FIELD_CAP = 40
_DETAIL_SAMPLE = 3


def _strip_suffix(name: str) -> str:
    """去掉业务名末尾的单据量词，便于模糊匹配：付款单->付款"""
    for suf in ("单", "表", "书", "记录"):
        if name.endswith(suf) and len(name) > len(suf):
            return name[: -len(suf)]
    return name


def _query_workflow_base(core: str, full: str) -> list[dict]:
    sql = (
        "select id, workflowname, formid from workflow_base "
        "where (workflowname like '%' || :c || '%' or workflowname like '%' || :f || '%') "
        "and formid is not null and rownum <= 20"
    )
    res = execute_select(sql, {"c": core, "f": full}, limit=20)
    if res.get("error"):
        return []
    cols = res["columns"]
    idx = {c: cols.index(c) for c in ("id", "workflowname", "formid") if c in cols}
    out = []
    for r in res["rows"]:
        try:
            out.append({
                "workflow_id": int(r[idx["id"]]),
                "workflow_name": r[idx["workflowname"]],
                "form_id": int(r[idx["formid"]]),
            })
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    return out


def _query_bill_by_label(core: str) -> list[dict]:
    """兜底：按表单中文名(htmllabelinfo.labelname)反查 workflow_bill"""
    sql = (
        "select b.id, b.tablename, b.namelabel, b.detailtablename "
        "from workflow_bill b join htmllabelinfo l "
        "on b.namelabel = l.indexid and l.languageid = :lang "
        "where l.labelname like '%' || :c || '%' and rownum <= 20"
    )
    res = execute_select(sql, {"c": core, "lang": LABEL_LANG_CN}, limit=20)
    if res.get("error"):
        return []
    cols = res["columns"]
    idx = {c: cols.index(c) for c in ("id", "tablename", "namelabel", "detailtablename") if c in cols}
    out = []
    for r in res["rows"]:
        try:
            out.append({
                "form_id": int(r[idx["id"]]),
                "table_name": r[idx["tablename"]],
                "name_label": int(r[idx["namelabel"]]) if r[idx["namelabel"]] is not None else None,
                "detail_table": r[idx["detailtablename"]],
            })
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    return out


def _get_bill(form_id: int) -> dict | None:
    res = execute_select(
        "select tablename, namelabel, detailtablename from workflow_bill where id = :f",
        {"f": form_id},
        limit=1,
    )
    if res.get("error") or not res["rows"]:
        return None
    cols = res["columns"]
    row = res["rows"][0]
    def g(c):
        return row[cols.index(c)] if c in cols else None
    return {
        "table_name": g("tablename"),
        "name_label": int(g("namelabel")) if g("namelabel") is not None else None,
        "detail_table": g("detailtablename"),
    }


def _get_fields(bill_id: int) -> list[dict]:
    res = execute_select(
        "select fieldname, fieldlabel, viewtype, detailtable, fielddbtype "
        "from workflow_billfield where billid = :b order by viewtype, dsporder",
        {"b": bill_id},
        limit=500,
    )
    if res.get("error"):
        return []
    cols = res["columns"]
    def g(c):
        return cols.index(c) if c in cols else None
    out = []
    for r in res["rows"]:
        out.append({
            "field": r[g("fieldname")] if g("fieldname") is not None else None,
            "field_label_id": int(r[g("fieldlabel")]) if g("fieldlabel") is not None and r[g("fieldlabel")] is not None else None,
            "viewtype": r[g("viewtype")] if g("viewtype") is not None else None,
            "detail_table": r[g("detailtable")] if g("detailtable") is not None else None,
            "db_type": r[g("fielddbtype")] if g("fielddbtype") is not None else None,
        })
    return out


def _physical_columns(table: str) -> list[str]:
    res = execute_select(
        "select column_name from all_tab_columns where table_name = :t order by column_id",
        {"t": table.upper()},
        limit=1000,
    )
    if res.get("error"):
        return []
    cols = res["columns"]
    ci = cols.index("column_name") if "column_name" in cols else 0
    return [r[ci] for r in res["rows"]]



def _pinyin_initials(text: str) -> str:
    """中文 -> 拼音首字母（检测委托单 -> jcwtd），非中文字符保留原样"""
    return "".join(lazy_pinyin(text, style=Style.FIRST_LETTER))


def _is_pinyin_abbr(name: str) -> bool:
    """纯 ASCII 字母（2-10 位），视为拼音缩写"""
    return bool(re.match(r"^[a-zA-Z]{2,10}$", name))


def _query_workflow_base_by_pinyin(abbr: str) -> list[dict]:
    """拼音缩写匹配：查全量 workflow_base，转拼音首字母后匹配"""
    abbr_lower = abbr.lower()
    sql = (
        "select id, workflowname, formid from workflow_base "
        "where formid is not null and workflowname is not null "
        "and rownum <= 500"
    )
    res = execute_select(sql, {}, limit=500)
    if res.get("error"):
        return []
    cols = res["columns"]
    idx = {k: cols.index(k) for k in ("id", "workflowname", "formid") if k in cols}
    out = []
    for r in res["rows"]:
        wf_name = r[idx["workflowname"]]
        if not wf_name:
            continue
        initials = _pinyin_initials(wf_name)
        # Match: abbreviation is substring of initials, or initials starts with abbreviation
        if abbr_lower in initials.lower():
            out.append({
                "workflow_id": r[idx["id"]],
                "workflow_name": wf_name,
                "form_id": r[idx["formid"]],
            })
    return out

def resolve_form_impl(business_name: str) -> dict:
    """按业务名解析自定义表单的物理表与字段，返回 dict（供 @tool 包装与测试复用）"""
    name = (business_name or "").strip()
    if not name:
        return {"error": "EMPTY_NAME", "detail": "business_name 不能为空"}
    core = _strip_suffix(name)

    base_rows = _query_workflow_base(core, name)
    form_ids = list(dict.fromkeys(r["form_id"] for r in base_rows))

    if not form_ids:
        for b in _query_bill_by_label(core):
            fid = b["form_id"]
            if fid not in form_ids:
                form_ids.append(fid)
                base_rows.append({"workflow_id": None, "workflow_name": None, "form_id": fid})

    # 拼音缩写匹配（如 jcwtd -> 检测委托单）
    if not form_ids and _is_pinyin_abbr(core):
        for r in _query_workflow_base_by_pinyin(core):
            fid = r["form_id"]
            if fid not in form_ids:
                form_ids.append(fid)
                base_rows.append(r)

    if not form_ids:
        return {
            "business_name": name,
            "matched_core": core,
            "matches": [],
            "note": "未匹配到流程或表单，建议换关键词或用 run_sql 直接查 workflow_base.workflowname。",
        }

    workflows_by_form: dict[int, list[dict]] = {}
    for r in base_rows:
        workflows_by_form.setdefault(r["form_id"], []).append({
            "workflow_id": r["workflow_id"],
            "workflow_name": r["workflow_name"],
        })

    label_ids: list[int] = []
    bill_cache: dict[int, dict] = {}
    for fid in form_ids:
        bill = _get_bill(fid)
        bill_cache[fid] = bill
        if bill and bill.get("name_label") is not None:
            label_ids.append(bill["name_label"])

    fields_by_form: dict[int, list[dict]] = {}
    for fid in form_ids:
        fields_by_form[fid] = _get_fields(fid)
        for f in fields_by_form[fid]:
            if f.get("field_label_id") is not None:
                label_ids.append(f["field_label_id"])

    labels = resolve_labels(label_ids)

    matches = []
    for fid in form_ids:
        bill = bill_cache.get(fid) or {}
        table = bill.get("table_name")
        form_label = labels.get(bill["name_label"]) if bill.get("name_label") is not None else None
        fields = fields_by_form.get(fid, [])
        main_fields = [f for f in fields if f.get("viewtype") == 0]
        detail_fields = [f for f in fields if f.get("viewtype") == 1]
        detail_groups: dict[str, list[dict]] = {}
        for f in detail_fields:
            dt = f.get("detail_table") or "unknown"
            detail_groups.setdefault(dt, []).append(f)

        def _label_of(f):
            lid = f.get("field_label_id")
            return labels.get(lid) if lid is not None else None

        main_out = [{
            "field": f["field"],
            "label": _label_of(f),
            "viewtype": "主表",
            "db_type": f.get("db_type"),
        } for f in main_fields[:_MAIN_FIELD_CAP]]
        main_truncated = len(main_fields) > _MAIN_FIELD_CAP

        detail_out = []
        for dt, fs in detail_groups.items():
            detail_out.append({
                "detail_table": dt,
                "field_count": len(fs),
                "sample_fields": [{
                    "field": f["field"],
                    "label": _label_of(f),
                    "db_type": f.get("db_type"),
                } for f in fs[:_DETAIL_SAMPLE]],
            })

        phys = _physical_columns(table) if table else []
        matches.append({
            "form_id": fid,
            "table_name": table,
            "form_label": form_label,
            "detail_table": bill.get("detail_table"),
            "workflows": workflows_by_form.get(fid, []),
            "physical_column_count": len(phys),
            "fields": {
                "main": main_out,
                "main_count_total": len(main_fields),
                "main_truncated": main_truncated,
                "detail_tables": detail_out,
                "detail_field_count_total": len(detail_fields),
            },
        })

    # 检索频率排序：高频表单排前面
    try:
        from app.agents.memory.neo4j_store import get_form_search_counts, increment_form_search
        table_names = [m.get("table_name") for m in matches if m.get("table_name")]
        if table_names:
            counts = get_form_search_counts(table_names)
            for m in matches:
                tbl = (m.get("table_name") or "").upper()
                m["search_count"] = counts.get(tbl, 0)
            matches.sort(key=lambda m: m.get("search_count", 0), reverse=True)
            for tn in table_names:
                increment_form_search(tn)
    except Exception:
        pass

    return {
        "business_name": name,
        "matched_core": core,
        "matches": matches,
    }


def get_form_detail_by_id(form_id: int) -> dict:
    """按 form_id 解析自定义表单的物理表与字段，供 @ 引用注入上下文复用。

    链路：workflow_bill(物理表 tablename + namelabel) -> htmllabelinfo(中文表名)
         -> workflow_billfield(字段 + 中文标签)。
    """
    bill = _get_bill(form_id)
    if not bill:
        return {"error": "NOT_FOUND", "detail": f"未找到 form_id={form_id} 的表单", "form_id": form_id}
    table = bill.get("table_name")
    fields = _get_fields(form_id)
    label_ids: list[int] = []
    if bill.get("name_label") is not None:
        label_ids.append(bill["name_label"])
    for f in fields:
        if f.get("field_label_id") is not None:
            label_ids.append(f["field_label_id"])
    labels = resolve_labels(label_ids)
    form_label = labels.get(bill["name_label"]) if bill.get("name_label") is not None else None
    main_fields = [f for f in fields if f.get("viewtype") == 0]
    detail_fields = [f for f in fields if f.get("viewtype") == 1]
    detail_groups: dict[str, list[dict]] = {}
    for f in detail_fields:
        dt = f.get("detail_table") or "unknown"
        detail_groups.setdefault(dt, []).append(f)

    def _label_of(f):
        lid = f.get("field_label_id")
        return labels.get(lid) if lid is not None else None

    main_out = [{
        "field": f["field"],
        "label": _label_of(f),
        "db_type": f.get("db_type"),
    } for f in main_fields]
    detail_out = []
    for dt, fs in detail_groups.items():
        detail_out.append({
            "detail_table": dt,
            "field_count": len(fs),
            "sample_fields": [{
                "field": f["field"],
                "label": _label_of(f),
                "db_type": f.get("db_type"),
            } for f in fs[:_DETAIL_SAMPLE]],
        })
    return {
        "form_id": form_id,
        "table": table,
        "label": form_label,
        "detail_table": bill.get("detail_table"),
        "main_fields": main_out,
        "main_count_total": len(main_fields),
        "main_truncated": False,
        "detail_tables": detail_out,
    }


def get_detail_table_fields(form_id: int, detail_table: str) -> dict:
    """按 form_id + 明细表名解析该明细表的字段，供 @ 引用明细表注入上下文复用。"""
    fields = _get_fields(form_id)
    dt = (detail_table or "").strip()
    dt_fields = [f for f in fields
                 if f.get("viewtype") == 1 and (f.get("detail_table") or "") == dt]
    if not dt_fields:
        dt_fields = [f for f in fields
                     if f.get("viewtype") == 1 and dt and dt in (f.get("detail_table") or "")]
    label_ids = [f["field_label_id"] for f in dt_fields
                 if f.get("field_label_id") is not None]
    labels = resolve_labels(label_ids)
    out = [{
        "field": f["field"],
        "label": labels.get(f["field_label_id"]) if f.get("field_label_id") is not None else None,
        "db_type": f.get("db_type"),
    } for f in dt_fields]
    return {
        "form_id": form_id,
        "detail_table": dt,
        "fields": out,
        "field_count": len(out),
    }


@tool
def resolve_form(purpose: str, business_name: str) -> str:
    """按业务名称解析 e-cology 自定义流程表单的物理表与字段（不查数据行）。

    purpose: 【必填】用一句中文写明本次解析的目的，例如"确认付款单对应哪张物理表与字段"。仅用于向用户展示意图，不参与执行。
    何时用：用户用业务名（如“付款单”“报销单”）指代一张表单、且需要知道它对应哪张物理表/哪些字段时。
    链路：workflow_base(流程名) -> formid -> workflow_bill(物理表 tablename + namelabel)
         -> htmllabelinfo(中文表名) -> workflow_billfield(字段 + 中文标签) -> all_tab_columns(物理列确认)。
    注意：自定义表单(流程表单/建模表单)不在数据字典内，只能靠本工具从线上库解析物理表。
    返回：JSON 字符串，含每个匹配表单的 form_id、table_name、form_label(中文名)、
         明细表、使用该表单的流程列表、字段(字段名+中文名+主表/明细+db类型)、物理列数。
         字段较多时主表字段返回前 40 个并标注 truncated，明细表按表分组返回字段数+样例。
    """
    result = resolve_form_impl(business_name)
    # 强制沉淀：表单元信息存入 Neo4j
    try:
        from app.agents.memory.knowledge import forced_deposit_form
        forms = result.get("forms", []) if isinstance(result, dict) else []
        for f in forms:
            if f.get("table_name"):
                forced_deposit_form(
                    form_name=f.get("form_label") or business_name,
                    table_name=f["table_name"],
                    workflow_id=str(f.get("form_id", "")),
                    detail_tables=[d.get("detail_table") for d in (f.get("detail_tables") or []) if d.get("detail_table")],
                )
    except Exception:
        pass  # 知识库沉淀失败不影响工具正常返回
    return json.dumps(result, ensure_ascii=False, default=str)

