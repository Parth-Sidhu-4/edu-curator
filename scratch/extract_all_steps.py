import json
import os

app_data_dir = r"C:\Users\parth\.gemini\antigravity"
conversation_id = "dfd193fc-e09d-46c7-af01-9237400b51bf"
log_path = os.path.join(app_data_dir, "brain", conversation_id, ".system_generated", "logs", "transcript.jsonl")

if not os.path.exists(log_path):
    print("No transcript.jsonl found")
    exit(1)

with open(log_path, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        try:
            data = json.loads(line)
            content = data.get("content", "")
            if "\\documentclass" in content:
                print(f"Step {idx}: type={data.get('type')}, source={data.get('source')}, length={len(content)}")
                # Print first 200 chars
                print("START:", content[:200].replace("\n", " "))
                # Print last 200 chars
                print("END:", content[-200:].replace("\n", " "))
                print("-" * 50)
        except:
            pass
