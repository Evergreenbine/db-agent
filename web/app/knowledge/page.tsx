"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import {
  ArrowLeftIcon,
  BrainIcon,
  LoaderIcon,
  PlusIcon,
  SearchIcon,
  Table2Icon,
  Trash2Icon,
  NetworkIcon,
  XIcon,
} from "lucide-react";
import Link from "next/link";

function apiBase(path: string): string {
  const host = typeof window !== "undefined" ? window.location.hostname : "localhost";
  return "http://" + host + ":8000" + path;
}

type Mem0Item = {
  id: string;
  store: string;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

type RelationItem = {
  id: string;
  store: string;
  src_table: string;
  src_field: string;
  tgt_table: string;
  tgt_field: string;
  relation_type: string;
  description: string;
  confidence: number;
  source: string;
  content: string;
};

type FormItem = {
  id: string;
  store: string;
  table: string;
  form_name: string;
  workflow_id: string;
  detail_tables: string[];
  content: string;
};

type TabKey = "mem0" | "relations" | "forms";

export default function KnowledgePage() {
  const [tab, setTab] = useState<TabKey>("mem0");
  const [loading, setLoading] = useState(true);
  const [mem0Items, setMem0Items] = useState<Mem0Item[]>([]);
  const [relations, setRelations] = useState<RelationItem[]>([]);
  const [forms, setForms] = useState<FormItem[]>([]);
  const [search, setSearch] = useState("");
  const [showAdd, setShowAdd] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(apiBase("/api/knowledge"));
      const j = await res.json();
      setMem0Items(j.mem0 || []);
      setRelations(j.neo4j_relations || []);
      setForms(j.neo4j_forms || []);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleDelete = async (store: string, id: string) => {
    if (!confirm("确认删除这条记忆？")) return;
    try {
      await fetch(apiBase("/api/knowledge"), {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ store, id }),
      });
      await fetchData();
    } catch {
      // ignore
    }
  };

  const filteredMem0 = mem0Items.filter((m) =>
    m.content.toLowerCase().includes(search.toLowerCase())
  );
  const filteredRels = relations.filter((r) =>
    r.content.toLowerCase().includes(search.toLowerCase())
  );
  const filteredForms = forms.filter((f) =>
    f.content.toLowerCase().includes(search.toLowerCase())
  );

  const tabs: { key: TabKey; label: string; icon: typeof BrainIcon; count: number }[] = [
    { key: "mem0", label: "语义记忆", icon: BrainIcon, count: mem0Items.length },
    { key: "relations", label: "表关系", icon: NetworkIcon, count: relations.length },
    { key: "forms", label: "表单元信息", icon: Table2Icon, count: forms.length },,
  ];

  return (
    <div className="flex h-dvh flex-col bg-background">
      {/* Header */}
      <header className="flex h-16 shrink-0 items-center gap-3 border-b px-6">
        <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground">
          <ArrowLeftIcon className="size-4" />
          返回
        </Link>
        <span className="text-lg font-semibold">记忆管理</span>
        <div className="ml-auto flex items-center gap-2">
          <div className="relative">
            <SearchIcon className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索记忆..."
              className="h-9 w-56 rounded-lg border bg-background pl-9 pr-3 text-sm outline-none focus:border-primary"
            />
          </div>
          <Button size="sm" variant="outline" onClick={() => setShowAdd(!showAdd)}>
            <PlusIcon className="mr-1 size-4" />
            {showAdd ? "收起" : "新增"}
          </Button>
        </div>
      </header>

      {/* Tabs */}
      <div className="flex shrink-0 gap-1 border-b px-6">
        {tabs.map((t) => {
          const Icon = t.icon;
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={"flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors " +
                (active ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground")}
            >
              <Icon className="size-4" />
              {t.label}
              <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{t.count}</span>
            </button>
          );
        })}
      </div>

      {/* Add form */}
      {showAdd && (
        <AddForm tab={tab} onSaved={() => { setShowAdd(false); fetchData(); }} />
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto px-6 py-4">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderIcon className="size-4 animate-spin" /> 加载中...
          </div>
        ) : tab === "mem0" ? (
          <Mem0List items={filteredMem0} onDelete={handleDelete} />
        ) : tab === "relations" ? (
          <RelationList items={filteredRels} onDelete={handleDelete} />
        ) : (
          <FormList items={filteredForms} onDelete={handleDelete} />
        )}
      </div>
    </div>
  );
}

function Mem0List({ items, onDelete }: { items: Mem0Item[]; onDelete: (s: string, id: string) => void }) {
  if (items.length === 0) {
    return <EmptyState text="还没有语义记忆。Agent 在对话中发现的知识会自动存入这里。" />;
  }
  return (
    <div className="space-y-2">
      {items.map((m) => (
        <div key={m.id} className="flex items-start gap-3 rounded-lg border bg-card p-3">
          <BrainIcon className="mt-0.5 size-4 shrink-0 text-blue-500" />
          <div className="min-w-0 flex-1">
            <p className="text-sm leading-relaxed">{m.content}</p>
            {m.created_at && (
              <p className="mt-1 text-[10px] text-muted-foreground">{m.created_at}</p>
            )}
          </div>
          <button
            onClick={() => onDelete("mem0", m.id)}
            className="shrink-0 rounded p-1 text-muted-foreground opacity-50 transition-opacity hover:bg-red-50 hover:text-red-600 hover:opacity-100"
            title="删除"
          >
            <Trash2Icon className="size-4" />
          </button>
        </div>
      ))}
    </div>
  );
}

function RelationList({ items, onDelete }: { items: RelationItem[]; onDelete: (s: string, id: string) => void }) {
  if (items.length === 0) {
    return <EmptyState text="还没有表关系记录。Agent 做跨表操作时会自动沉淀表关系。" />;
  }
  return (
    <div className="space-y-2">
      {items.map((r) => (
        <div key={r.id} className="flex items-start gap-3 rounded-lg border bg-card p-3">
          <NetworkIcon className="mt-0.5 size-4 shrink-0 text-purple-500" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-sm">
              <span className="font-mono font-medium text-blue-600">{r.src_table}.{r.src_field}</span>
              <span className="text-muted-foreground">-&gt;</span>
              <span className="font-mono font-medium text-green-600">{r.tgt_table}.{r.tgt_field}</span>
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{r.relation_type}</span>
              {r.source === "system_forced" && (
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-700">强制沉淀</span>
              )}
            </div>
            {r.description && <p className="mt-1 text-xs text-muted-foreground">{r.description}</p>}
            <p className="mt-0.5 text-[10px] text-muted-foreground">置信度: {r.confidence}</p>
          </div>
          <button
            onClick={() => onDelete("neo4j_relation", r.id)}
            className="shrink-0 rounded p-1 text-muted-foreground opacity-50 transition-opacity hover:bg-red-50 hover:text-red-600 hover:opacity-100"
            title="删除"
          >
            <Trash2Icon className="size-4" />
          </button>
        </div>
      ))}
    </div>
  );
}

function FormList({ items, onDelete }: { items: FormItem[]; onDelete: (s: string, id: string) => void }) {
  if (items.length === 0) {
    return <EmptyState text="还没有表单元信息。Agent 解析表单时会自动沉淀。" />;
  }
  return (
    <div className="space-y-2">
      {items.map((f) => (
        <div key={f.id} className="flex items-start gap-3 rounded-lg border bg-card p-3">
          <Table2Icon className="mt-0.5 size-4 shrink-0 text-orange-500" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-sm">
              <span className="font-medium">{f.form_name}</span>
              <span className="font-mono text-xs text-muted-foreground">{f.table}</span>
            </div>
            <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-muted-foreground">
              {f.workflow_id && <span>流程编号: {f.workflow_id}</span>}
              {f.detail_tables.length > 0 && <span>明细表: {f.detail_tables.join(", ")}</span>}
            </div>
          </div>
          <button
            onClick={() => onDelete("neo4j_form", f.id)}
            className="shrink-0 rounded p-1 text-muted-foreground opacity-50 transition-opacity hover:bg-red-50 hover:text-red-600 hover:opacity-100"
            title="删除"
          >
            <Trash2Icon className="size-4" />
          </button>
        </div>
      ))}
    </div>
  );
}



function AddForm({ tab, onSaved }: { tab: TabKey; onSaved: () => void }) {
  const [saving, setSaving] = useState(false);

  // Mem0 form state
  const [memContent, setMemContent] = useState("");

  // Relation form state
  const [rel, setRel] = useState({ src_table: "", src_field: "", tgt_table: "", tgt_field: "", relation_type: "join", description: "" });

  // Form meta state
  const [form, setForm] = useState({ form_name: "", table: "", workflow_id: "", detail_tables: "" });

  const handleSave = async () => {
    setSaving(true);
    try {
      let body: Record<string, unknown> = {};
      if (tab === "mem0") {
        if (!memContent.trim()) return;
        body = { store: "mem0", content: memContent };
      } else if (tab === "relations") {
        if (!rel.src_table || !rel.tgt_table) return;
        body = { store: "neo4j_relation", ...rel };
      } else {
        if (!form.form_name || !form.table) return;
        body = { store: "neo4j_form", ...form };
      }
      await fetch(apiBase("/api/knowledge"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      // Reset
      setMemContent("");
      setRel({ src_table: "", src_field: "", tgt_table: "", tgt_field: "", relation_type: "join", description: "" });
      setForm({ form_name: "", table: "", workflow_id: "", detail_tables: "" });
      onSaved();
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  };

  const inputCls = "h-9 rounded-lg border bg-background px-3 text-sm outline-none focus:border-primary";

  return (
    <div className="shrink-0 border-b bg-muted/30 px-6 py-3">
      <div className="flex items-center gap-2">
        {tab === "mem0" && (
          <input
            value={memContent}
            onChange={(e) => setMemContent(e.target.value)}
            placeholder="输入要记住的业务知识，如：formtable_main_238 是请假单主表，通过 id 关联明细表 formtable_main_238_dt1"
            className={inputCls + " flex-1"}
          />
        )}
        {tab === "relations" && (
          <div className="flex flex-1 flex-wrap items-center gap-2">
            <input value={rel.src_table} onChange={(e) => setRel({ ...rel, src_table: e.target.value })} placeholder="源表名" className={inputCls + " w-36"} />
            <input value={rel.src_field} onChange={(e) => setRel({ ...rel, src_field: e.target.value })} placeholder="源字段" className={inputCls + " w-24"} />
            <span className="text-muted-foreground">-&gt;</span>
            <input value={rel.tgt_table} onChange={(e) => setRel({ ...rel, tgt_table: e.target.value })} placeholder="目标表名" className={inputCls + " w-36"} />
            <input value={rel.tgt_field} onChange={(e) => setRel({ ...rel, tgt_field: e.target.value })} placeholder="目标字段" className={inputCls + " w-24"} />
            <select value={rel.relation_type} onChange={(e) => setRel({ ...rel, relation_type: e.target.value })} className={inputCls + " w-24"}>
              <option value="join">join</option>
              <option value="foreign_key">foreign_key</option>
              <option value="main_detail">main_detail</option>
            </select>
            <input value={rel.description} onChange={(e) => setRel({ ...rel, description: e.target.value })} placeholder="说明（可选）" className={inputCls + " w-40"} />
          </div>
        )}
        {tab === "forms" && (
          <div className="flex flex-1 flex-wrap items-center gap-2">
            <input value={form.form_name} onChange={(e) => setForm({ ...form, form_name: e.target.value })} placeholder="表单中文名" className={inputCls + " w-32"} />
            <input value={form.table} onChange={(e) => setForm({ ...form, table: e.target.value })} placeholder="物理表名" className={inputCls + " w-40"} />
            <input value={form.workflow_id} onChange={(e) => setForm({ ...form, workflow_id: e.target.value })} placeholder="流程编号" className={inputCls + " w-24"} />
            <input value={form.detail_tables} onChange={(e) => setForm({ ...form, detail_tables: e.target.value })} placeholder="明细表（逗号分隔）" className={inputCls + " w-40"} />
          </div>
        )}
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {saving ? <LoaderIcon className="size-4 animate-spin" /> : "保存"}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => onSaved()}>
          <XIcon className="size-4" />
        </Button>
      </div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="mb-3 rounded-full bg-muted p-4">
        <BrainIcon className="size-8 text-muted-foreground" />
      </div>
      <p className="max-w-xs text-sm text-muted-foreground">{text}</p>
    </div>
  );
}
