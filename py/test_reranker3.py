import importlib.util, os
spec = importlib.util.spec_from_file_location("reranker", "app/agents/memory/reranker.py")
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)

query = "出差外勤表 formtable_main_17 字段用途 表关系 业务规则 报账 流程"
mems = [
    {"memory": "出差外勤表 formtable_main_17 的报销金额字段 bxje 关联财务报账表 formtable_main_19，出差类型 cclx 区分市内出差和外省出差", "score": 0.78},
    {"memory": "检测委托单 formtable_main_257 主表字段 cbzx 是浏览按钮字段，来源表为 UF_CBZXNBDDH", "score": 0.55},
    {"memory": "出差申请单 formtable_main_17 审批通过后 djzt=2 时推送出差记录到 kq_business_trip 表", "score": 0.72},
    {"memory": "kq_leave 表存储请假记录，通过 requestid 关联 workflow_request 表", "score": 0.48},
    {"memory": "绩效组织管理 UF_PERFORMANCEORG 表的 fgjbypslc 字段控制分管级本月评审流程", "score": 0.51},
    {"memory": "加班申请 formtable_main_171 加班类型 classno 推送到 kq_overtime 表", "score": 0.46},
]
print("查询:", query)
print("输入:", len(mems), "条")
for i, m in enumerate(mems, 1):
    print(f"  [{i}] score={m['score']:.2f} | {m['memory'][:55]}")
print()
out = r.rerank_memories(query, mems)
print("输出:", len(out), "条 (过滤掉", len(mems) - len(out), "条)")
for i, m in enumerate(out, 1):
    print(f"  [{i}] score={m['score']:.2f} | {m['memory'][:55]}")
