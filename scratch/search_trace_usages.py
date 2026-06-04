with open("d:/Internship/dashboard/app.js", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("=== state.traces USAGE ===")
for i, line in enumerate(lines):
    if "state.traces" in line or "fetchTraces" in line:
        print(f"Line {i+1}: {line.strip()}")
