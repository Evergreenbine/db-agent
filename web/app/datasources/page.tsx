"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import {
  ArrowLeftIcon,
  CheckIcon,
  ChevronDownIcon,
  DatabaseIcon,
  LoaderIcon,
  PlusIcon,
  Trash2Icon,
  XIcon,
} from "lucide-react";

type DataSource = {
  id: number;
  name: string;
  db_type: string;
  host: string;
  port: number;
  database_name: string;
  username: string;
  description: string;
  is_active: boolean;
  created_at: string;
};

type TestResult = { ok: boolean; message: string; tables_count: number } | null;
type TableInfo = { name: string; row_count: number; is_backup: boolean };
type DiscoverResult = { total: number; tables: TableInfo[]; truncated: boolean; error?: string } | null;

const TYPE_LABELS: Record<string, string> = {
  oracle: "Oracle",
  sqlserver: "SQL Server",
  mysql: "MySQL",
};

const TYPE_BADGES: Record<string, string> = {
  oracle: "border-red-200 bg-red-50 text-red-700",
  sqlserver: "border-blue-200 bg-blue-50 text-blue-700",
  mysql: "border-green-200 bg-green-50 text-green-700",
};

const FALLBACK_TYPES = [
  { value: "oracle", label: "Oracle", default_port: 1521, db_label: "SID" },
  { value: "sqlserver", label: "SQL Server", default_port: 1433, db_label: "数据库名" },
  { value: "mysql", label: "MySQL", default_port: 3306, db_label: "数据库名" },
];

function apiBase(path: string): string {
  const host = typeof window !== "undefined" ? window.location.hostname : "localhost";
  return "http://" + host + ":8000" + path;
}

export default function DataSourcesPage() {
  const [sources, setSources] = useState<DataSource[]>([]);
  const [types, setTypes] = useState<typeof FALLBACK_TYPES>(FALLBACK_TYPES);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    name: "",
    db_type: "sqlserver",
    host: "",
    port: 1433,
    database_name: "",
    username: "",
    password: "",
    description: "",
  });
  const [testResults, setTestResults] = useState<Record<number, TestResult>>({});
  const [testing, setTesting] = useState<Record<number, boolean>>({});
  const [discoverResults, setDiscoverResults] = useState<Record<number, DiscoverResult>>({});
  const [discovering, setDiscovering] = useState<Record<number, boolean>>({});
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  const fetchSources = async () => {
    try {
      const res = await fetch(apiBase("/api/datasource"));
      const data = await res.json();
      setSources(data.datasources || []);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSources();
    fetch(apiBase("/api/datasource/types"))
      .then((r) => r.json())
      .then((d) => setTypes(d.types?.length ? d.types : FALLBACK_TYPES))
      .catch(() => {});
  }, []);

  const handleTypeChange = (dbType: string) => {
    const t = types.find((x) => x.value === dbType);
    setForm((f) => ({ ...f, db_type: dbType, port: t?.default_port ?? f.port }));
  };

  const handleAdd = async () => {
    setSaving(true);
    try {
      const res = await fetch(apiBase("/api/datasource"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!data.error) {
        setShowForm(false);
        setForm({ name: "", db_type: "sqlserver", host: "", port: 1433, database_name: "", username: "", password: "", description: "" });
        await fetchSources();
      } else {
        alert(data.detail || data.error);
      }
    } catch (e) {
      alert(String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (id: number) => {
    setTesting((t) => ({ ...t, [id]: true }));
    try {
      const res = await fetch(apiBase("/api/datasource/" + id + "/test"), { method: "POST" });
      const data = await res.json();
      setTestResults((r) => ({ ...r, [id]: data }));
    } catch (e) {
      setTestResults((r) => ({ ...r, [id]: { ok: false, message: String(e), tables_count: 0 } }));
    } finally {
      setTesting((t) => ({ ...t, [id]: false }));
    }
  };

  const handleDiscover = async (id: number) => {
    setDiscovering((d) => ({ ...d, [id]: true }));
    try {
      const res = await fetch(apiBase("/api/datasource/" + id + "/discover"), { method: "POST" });
      const data = await res.json();
      setDiscoverResults((d) => ({ ...d, [id]: data }));
      setExpanded((e) => ({ ...e, [id]: true }));
    } catch (e) {
      setDiscoverResults((d) => ({ ...d, [id]: { total: 0, tables: [], truncated: false, error: String(e) } }));
    } finally {
      setDiscovering((d) => ({ ...d, [id]: false }));
    }
  };

  const handleDelete = async (id: number, name: string) => {
    if (!window.confirm("确认删除数据源「" + name + "」？")) return;
    await fetch(apiBase("/api/datasource/" + id), { method: "DELETE" });
    await fetchSources();
  };

  const inputCls = "w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-200";
  const labelCls = "mb-1 block text-xs font-medium text-zinc-500";

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="border-b bg-white px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-center gap-3">
          {onBack ? (
            <button onClick={onBack} className="text-zinc-400 hover:text-zinc-700" style={{ cursor: "pointer" }}>
              <ArrowLeftIcon className="size-5" />
            </button>
          ) : (
            <a href="/" className="text-zinc-400 hover:text-zinc-700" style={{ cursor: "pointer" }}>
              <ArrowLeftIcon className="size-5" />
            </a>
          )}
          <DatabaseIcon className="size-5 text-blue-600" />
          <h1 className="text-lg font-semibold">数据源管理</h1>
          <Button size="sm" className="ml-auto bg-blue-600 hover:bg-blue-700 text-white" onClick={() => setShowForm((s) => !s)}>
            <PlusIcon className="mr-1 size-4" />
            添加数据源
          </Button>
        </div>
      </div>

      <div className="mx-auto max-w-3xl space-y-4 p-6">
        {showForm && (
          <div className="rounded-xl border bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-semibold">新建数据源</h2>
              <button onClick={() => setShowForm(false)} style={{ cursor: "pointer" }}>
                <XIcon className="size-4 text-zinc-400" />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={labelCls}>名称</label>
                <input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="如 hr / finance" />
              </div>
              <div>
                <label className={labelCls}>数据库类型</label>
                <select className={inputCls} value={form.db_type} onChange={(e) => handleTypeChange(e.target.value)} style={{ cursor: "pointer" }}>
                  {types.map((t) => (<option key={t.value} value={t.value}>{t.label}</option>))}
                </select>
              </div>
              <div>
                <label className={labelCls}>主机地址</label>
                <input className={inputCls} value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} placeholder="10.3.10.86" />
              </div>
              <div>
                <label className={labelCls}>端口</label>
                <input className={inputCls} type="number" value={form.port} onChange={(e) => setForm({ ...form, port: parseInt(e.target.value) || 0 })} />
              </div>
              <div className="col-span-2">
                <label className={labelCls}>{form.db_type === "oracle" ? "SID" : "数据库名"}</label>
                <input className={inputCls} value={form.database_name} onChange={(e) => setForm({ ...form, database_name: e.target.value })} placeholder={form.db_type === "oracle" ? "ORCL" : "G4PRO"} />
              </div>
              <div>
                <label className={labelCls}>用户名</label>
                <input className={inputCls} value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
              </div>
              <div>
                <label className={labelCls}>密码</label>
                <input className={inputCls} type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              </div>
              <div className="col-span-2">
                <label className={labelCls}>描述（可选）</label>
                <input className={inputCls} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="如 人事数据库" />
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setShowForm(false)}>取消</Button>
              <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-white" disabled={saving || !form.name || !form.host} onClick={handleAdd}>
                {saving ? <LoaderIcon className="mr-1 size-4 animate-spin" /> : <CheckIcon className="mr-1 size-4" />}
                保存
              </Button>
            </div>
          </div>
        )}

        {loading ? (
          <div className="py-12 text-center text-sm text-zinc-400">加载中…</div>
        ) : sources.length === 0 ? (
          <div className="py-12 text-center text-sm text-zinc-400">暂无数据源，点击右上角添加</div>
        ) : (
          sources.map((ds) => {
            const tr = testResults[ds.id];
            const dr = discoverResults[ds.id];
            const badgeCls = TYPE_BADGES[ds.db_type] || "border-zinc-200 bg-zinc-50 text-zinc-600";
            return (
              <div key={ds.id} className="rounded-xl border bg-white p-5 shadow-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-base font-semibold">{ds.name}</span>
                  <span className={"rounded-md border px-2 py-0.5 text-xs font-medium " + badgeCls}>
                    {TYPE_LABELS[ds.db_type] || ds.db_type}
                  </span>
                  {ds.description && <span className="text-xs text-zinc-400">{ds.description}</span>}
                  <div className="ml-auto flex gap-2">
                    <Button variant="outline" size="sm" disabled={testing[ds.id]} onClick={() => handleTest(ds.id)}>
                      {testing[ds.id] ? <LoaderIcon className="mr-1 size-3.5 animate-spin" /> : null}
                      测试连接
                    </Button>
                    <Button variant="outline" size="sm" disabled={discovering[ds.id]} onClick={() => handleDiscover(ds.id)}>
                      {discovering[ds.id] ? <LoaderIcon className="mr-1 size-3.5 animate-spin" /> : null}
                      发现表
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => handleDelete(ds.id, ds.name)}>
                      <Trash2Icon className="size-3.5 text-red-500" />
                    </Button>
                  </div>
                </div>
                <div className="mt-2 font-mono text-xs text-zinc-400">
                  {ds.host}:{ds.port} / {ds.database_name}  ({ds.username})
                </div>
                {tr && (
                  <div className={"mt-3 rounded-lg border px-3 py-2 text-xs " + (tr.ok ? "border-green-200 bg-green-50 text-green-700" : "border-red-200 bg-red-50 text-red-700")}>
                    {tr.ok ? "✓ " + tr.message : "✗ " + tr.message}
                  </div>
                )}
                {dr && !dr.error && (
                  <div className="mt-3">
                    <button
                      className="flex items-center gap-1 text-xs font-medium text-zinc-500"
                      onClick={() => setExpanded((e) => ({ ...e, [ds.id]: !e[ds.id] }))}
                      style={{ cursor: "pointer" }}
                    >
                      <ChevronDownIcon className={"size-3 transition-transform " + (expanded[ds.id] ? "" : "-rotate-90")} />
                      发现 {dr.total} 张表{dr.truncated ? "（仅显示前 200）" : ""}
                    </button>
                    {expanded[ds.id] && dr.tables && dr.tables.length > 0 && (
                      <div className="relative mt-2 max-h-48 overflow-auto rounded-lg border">
                        <table className="w-full text-xs">
                          <thead className="sticky top-0 bg-zinc-50 text-zinc-500">
                            <tr>
                              <th className="px-3 py-1.5 text-left font-medium">表名</th>
                              <th className="px-3 py-1.5 text-right font-medium">行数</th>
                              <th className="px-3 py-1.5 text-left font-medium">类型</th>
                            </tr>
                          </thead>
                          <tbody>
                            {dr.tables.slice(0, 100).map((t, i) => (
                              <tr key={i} className="border-t border-zinc-100">
                                <td className="px-3 py-1.5 font-mono">{t.name}</td>
                                <td className="px-3 py-1.5 text-right tabular-nums text-zinc-400">{(t.row_count ?? 0).toLocaleString()}</td>
                                <td className="px-3 py-1.5">
                                  {t.is_backup ? <span className="text-amber-600">备份</span> : <span className="text-green-600">业务</span>}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        <div className="pointer-events-none absolute right-0 top-0 h-full w-7" style={{ background: "linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.95) 100%)" }} />
                      </div>
                    )}
                  </div>
                )}
                {dr?.error && (
                  <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{dr.error}</div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
