import pyodbc, re, sys
conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};SERVER=10.3.10.86,1433;DATABASE=G4PRO;UID=oa13;PWD=Oa13sql788;",
    timeout=15
)
cur = conn.cursor()
cur.execute("""
SELECT t.name, ISNULL(p.rows,0)
FROM sys.tables t
LEFT JOIN sys.partitions p ON t.object_id=p.object_id AND p.index_id IN (0,1)
ORDER BY p.rows DESC
""")
rows = cur.fetchall()

# classify by prefix
cats = {"hr_":[],"kq_":[],"gz_":[],"sal_":[],"sys_":[],"other":[]}
backup_pat = re.compile(r'(bk$|_bak|_copy|_202\d|Before|backup|_old|temp)', re.I)
for tn, rc in rows:
    key = "other"
    for p in ["hr_","kq_","gz_","sal_","sys_"]:
        if tn.lower().startswith(p): key = p; break
    is_bak = bool(backup_pat.search(tn))
    cats[key].append((tn, rc, is_bak))

labels = {"hr_":"人事(HR)","kq_":"考勤(Attendance)","gz_":"工资(Salary)","sal_":"薪资(Salary2)","sys_":"系统(System)","other":"其他(Other)"}
total_biz = 0
total_bak = 0
for key in ["hr_","kq_","gz_","sal_","sys_","other"]:
    items = cats[key]
    biz = [x for x in items if not x[2]]
    bak = [x for x in items if x[2]]
    total_biz += len(biz); total_bak += len(bak)
    print(f"\n=== {labels[key]}: {len(biz)} 业务表 + {len(bak)} 备份/临时 ===")
    for tn, rc, is_bak in items:
        tag = " [BAK]" if is_bak else ""
        print(f"  {tn:45s} {rc:>10,}{tag}")

print(f"\n=== TOTAL: {total_biz} business + {total_bak} backup/temp = {len(rows)} ===")
conn.close()
