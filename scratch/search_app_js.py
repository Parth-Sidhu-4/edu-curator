with open("d:/Internship/dashboard/app.js", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("=== LLM_TRACES OCCURRENCES ===")
for i, line in enumerate(lines):
    if "llm_traces" in line:
        print(f"Line {i+1}: {line.strip()}")

print("=== SUPABASE FROM SELECT OCCURRENCES ===")
for i, line in enumerate(lines):
    if ".from(" in line and "select" in line:
        print(f"Line {i+1}: {line.strip()}")
