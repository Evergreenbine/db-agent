import importlib.util, os
spec = importlib.util.spec_from_file_location("reranker", "app/agents/memory/reranker.py")
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)

query = "请假单审批通过后推送人事库kq_leave，字段对应关系是什么"
mems = [
    {"memory": "请假申请单 formtable_main_238 的 djzt=2 时触发推送到人事库 kq_leave 表，通过 kq_leave.remark 存储 formtable_main_238.sqbh 做关联", "score": 0.82},
    {"memory": "检测委托单 formtable_main_257 主表字段 cbzx 来源表为 UF_CBZXNBDDH", "score": 0.61},
    {"memory": "kq_leave 表存储请假记录，并通过 requestid 字段关联到 workflow_request 表", "score": 0.73},
    {"memory": "加班申请 formtable_main_171 的加班类型字段 classno 推送到 kq_overtime 表", "score": 0.55},
    {"memory": "付款申请单 formtable_main_19 的供应商编号 gysbh 和收款单位 skdw1 字段", "score": 0.48},
]
print("查询:", query)
print("输入:", len(mems), "条")
for i, m in enumerate(mems, 1):
    print(f"  [{i}] score={m['score']:.2f} | {m['memory'][:50]}")
print()
out = r.rerank_memories(query, mems)
print("输出:", len(out), "条 (过滤掉", len(mems) - len(out), "条)")
for i, m in enumerate(out, 1):
    print(f"  [{i}] score={m['score']:.2f} | {m['memory'][:50]}")
