import urllib.request, json
try:
    r = urllib.request.urlopen("http://127.0.0.1:8000/api/forms", timeout=30)
    data = json.loads(r.read())
    w = data.get("workflow", [])[:3]
    for item in w:
        name = item.get("chinese_name", "")
        segs = item.get("segments", [])
        print(f"name={name} segments={segs}")
    total = len(data.get("workflow", []))
    print(f"Total workflow forms: {total}")
except Exception as e:
    print(f"Error: {e}")
