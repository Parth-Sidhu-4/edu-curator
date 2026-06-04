import sys
sys.stdout.reconfigure(encoding='utf-8')

file_path = "dashboard/api.js"
with open(file_path, "r", encoding="utf-8") as f:
    for line_num, line in enumerate(f, 1):
        if "submitReviewAction" in line or "apiPost('/api/review'" in line:
            print(f"{line_num}: {line.strip()}")
