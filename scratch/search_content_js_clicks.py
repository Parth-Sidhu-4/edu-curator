import sys

# Reconfigure stdout to use utf-8 to prevent encoding errors on Windows
sys.stdout.reconfigure(encoding='utf-8')

file_path = "dashboard/views/content.js"
with open(file_path, "r", encoding="utf-8") as f:
    for line_num, line in enumerate(f, 1):
        if any(w in line for w in ["Save", "Click", "submit", "click", "Approve", "error", "fail"]):
            print(f"{line_num}: {line.strip()}")
