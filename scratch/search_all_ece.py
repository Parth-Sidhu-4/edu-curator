import os

def search_files(dir_path):
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    if "signal theory" in content or "noisy channel" in content or "Electronics and Communication" in content:
                        print(f"Found in: {file_path} (size={len(content)})")
            except Exception as e:
                pass

print("Searching d:\\Internship...")
search_files("d:\\Internship")
print("Searching brain directory...")
search_files(r"C:\Users\parth\.gemini\antigravity\brain")
