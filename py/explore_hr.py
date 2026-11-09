import pyodbc, json, sys

conn_str = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=10.3.10.86,1433;"
    "DATABASE=G4PRO;"
    "UID=oa13;"
    "PWD=Oa13sql788;"
)
try:
    conn = pyodbc.connect(conn_str, timeout=15)
except Exception as e:
    print("CONNECT_FAIL:", e); sys.exit(1)

cur = conn.cursor()

# 1) All user tables + row counts
cur.execute("""
SELECT s.name AS schema_name, t.name AS table_name,
       ISNULL(p.rows,0) AS row_count,
       CAST(ep.value AS NVARCHAR(500)) AS table_desc
FROM sys.tables t
JOIN sys.schemas s ON t.schema_id = s.schema_id
LEFT JOIN sys.partitions p ON t.object_id = p.object_id AND p.index_id IN (0,1)
LEFT JOIN sys.extended_properties ep ON ep.major_id = t.object_id AND ep.minor_id = 0 AND ep.name = 'MS_Description'
ORDER BY p.rows DESC, s.name, t.name
""")
tables = cur.fetchall()
print(f"=== TABLES: {len(tables)} ===")
for r in tables:
    desc = ("  -- " + r.table_desc.strip()) if r.table_desc and r.table_desc.strip() else ""
    print(f"[{r.schema_name}] {r.table_name:40s} rows={r.row_count:>8}{desc}")

# 2) Extended properties summary (how many tables/cols have descriptions)
cur.execute("SELECT COUNT(*) FROM sys.extended_properties WHERE class=1")
ep_count = cur.fetchone()[0]
print(f"\n=== EXTENDED_PROPERTIES count: {ep_count} ===")

# 3) Columns with descriptions for top 30 tables by row count
print("\n=== COLUMNS (top 30 tables by rows) ===")
for r in tables[:30]:
    tn = r.table_name
    sn = r.schema_name
    cur.execute("""
    SELECT c.name, ty.name AS data_type, c.max_length, c.is_nullable,
           CAST(ep.value AS NVARCHAR(200)) AS col_desc
    FROM sys.columns c
    JOIN sys.types ty ON c.user_type_id = ty.user_type_id
    LEFT JOIN sys.extended_properties ep ON ep.major_id = c.object_id AND ep.minor_id = c.column_id AND ep.name = 'MS_Description'
    WHERE c.object_id = OBJECT_ID(?)
    ORDER BY c.column_id
    """, f"[{sn}].[{tn}]")
    cols = cur.fetchall()
    print(f"\n[{sn}].[{tn}]  ({r.row_count} rows){('  -- '+r.table_desc.strip()) if r.table_desc and r.table_desc.strip() else ''}")
    for c in cols:
        nullable = "NULL" if c.is_nullable else "NOT NULL"
        ml = f"({c.max_length})" if c.max_length != -1 and c.data_type in ('varchar','nvarchar','char','nchar','varbinary') else ""
        cd = f"  /* {c.col_desc.strip()} */" if c.col_desc and c.col_desc.strip() else ""
        print(f"  {c.name:30s} {c.data_type}{ml:8s} {nullable}{cd}")

conn.close()
print("\n=== DONE ===")
