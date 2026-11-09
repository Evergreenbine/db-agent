"""测试重排序模块 - 直接加载 reranker 避免触发 Qdrant 锁"""
import importlib.util
import os

# 直接加载 reranker 模块，绕过 app.agents.memory.__init__ 的 import 链
spec = importlib.util.spec_from_file_location(
    "reranker",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "agents", "memory", "reranker.py"),
)
reranker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reranker)

# 模拟之前实际查出来的记忆（检测委托单成本中心查询的结果）
test_query = "检测委托单 项目成本中心 cbzx 引用哪个表单"
test_memories = [
    {
        "memory": "检测委托单(formtable_main_257)主表字段 cbzx 是浏览按钮字段，通过 mode_browser 定义的浏览器取数，来源表为建模表单 UF_CBZXNBDDH",
        "score": 0.707,
    },
    {
        "memory": "kq_leave 表位于 datasource=hr 数据源中，请假申请单 formtable_main_238 的 djzt=2 时推送请假数据至该表",
        "score": 0.562,
    },
    {
        "memory": "请假申请单 formtable_main_238 的 djzt=2 时触发推送到人事库 kq_leave 表",
        "score": 0.514,
    },
    {
        "memory": "kq_leave 表存储请假记录，并通过 requestid 字段关联到 workflow_request 表",
        "score": 0.487,
    },
]

print("=" * 60)
print("测试查询:", test_query)
print("=" * 60)
print(f"\n输入: {len(test_memories)} 条候选记忆")
for i, m in enumerate(test_memories, 1):
    print(f"  记忆{i} (score={m['score']:.3f}): {m['memory'][:60]}...")

print(f"\nOllama 可用: {reranker.is_available()}")

print("\n开始重排序...")
filtered = reranker.rerank_memories(test_query, test_memories)

print(f"\n输出: {len(filtered)} 条相关记忆")
for i, m in enumerate(filtered, 1):
    print(f"  记忆{i} (score={m['score']:.3f}): {m['memory'][:60]}...")

print(f"\n过滤掉了 {len(test_memories) - len(filtered)} 条不相关记忆")
