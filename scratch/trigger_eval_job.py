import urllib.request
import json
import sys
from pathlib import Path

sys.path.append(str(Path("D:/Internship/src")))
from edu_curator.cli import _topic_uuid

topic_id = _topic_uuid(4)
print(f"Triggering evaluation for topic ID: {topic_id} (SN 4)")

url = "http://localhost:8502/api/evaluate"
data = json.dumps({"topic_id": topic_id}).encode("utf-8")

req = urllib.request.Request(
    url,
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    with urllib.request.urlopen(req) as res:
        print("Response Code:", res.getcode())
        print("Response Body:", res.read().decode("utf-8"))
except Exception as e:
    print("Error:", e)
