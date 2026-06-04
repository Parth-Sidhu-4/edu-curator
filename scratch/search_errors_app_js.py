with open("d:/Internship/dashboard/app.js", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("=== TOAST FUNCTION DEFINITION ===")
for i, line in enumerate(lines):
    if "function toast(" in line:
        print(f"Line {i+1}: {line.strip()}")

print("=== error.message SNIPPETS ===")
for i, line in enumerate(lines):
    if "error.message" in line:
        print(f"Line {i+1}: {line.strip()}")
