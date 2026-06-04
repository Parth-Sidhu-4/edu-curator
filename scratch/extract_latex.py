import json
import os

app_data_dir = r"C:\Users\parth\.gemini\antigravity"
conversation_id = "dfd193fc-e09d-46c7-af01-9237400b51bf"
log_path = os.path.join(app_data_dir, "brain", conversation_id, ".system_generated", "logs", "transcript.jsonl")

if not os.path.exists(log_path):
    print(f"Log path does not exist: {log_path}")
    exit(1)

with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            # We want to find the latest text that contains the latex document
            content = data.get("content", "")
            if "\\documentclass[12pt,a4paper]{article}" in content:
                # The user's input might be in content or in tool_calls or error messages.
                # Let's check where the longest match is.
                # Let's write the found content to scratch/user_input.tex
                with open("scratch/user_input.tex", "w", encoding="utf-8") as out:
                    out.write(content)
                print("Successfully extracted LaTeX document to scratch/user_input.tex")
                print("Length of content:", len(content))
        except Exception as e:
            pass
