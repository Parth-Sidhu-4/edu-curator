import json
import os

app_data_dir = r"C:\Users\parth\.gemini\antigravity"
conversation_id = "dfd193fc-e09d-46c7-af01-9237400b51bf"
log_path = os.path.join(app_data_dir, "brain", conversation_id, ".system_generated", "logs", "transcript.jsonl")

if not os.path.exists(log_path):
    print(f"Log path does not exist: {log_path}")
    exit(1)

user_messages = []
with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get("type") == "USER_INPUT" or (data.get("source") == "USER_EXPLICIT" and "content" in data):
                user_messages.append(data)
        except Exception as e:
            pass

if not user_messages:
    print("No user messages found.")
    exit(0)

last_msg = user_messages[-1]
content = last_msg.get("content", "")
print("LAST USER MESSAGE LENGTH:", len(content))
with open("scratch/latest_user_request.txt", "w", encoding="utf-8") as out:
    out.write(content)
print("Saved to scratch/latest_user_request.txt")
