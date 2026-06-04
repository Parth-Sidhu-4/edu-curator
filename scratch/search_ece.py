import os

def search_files(dir_path):
    for root, dirs, files in os.walk(dir_path):
        if ".git" in root or ".system_generated" in root or ".pytest_cache" in root:
            continue
        for file in files:
            if file.endswith(".tex") or file.endswith(".md") or file.endswith(".txt"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        if "Electronics and Communication" in content or "noisy channel" in content:
                            print(f"Found in: {file_path}")
                except Exception as e:
                    pass

print("Searching d:\\Internship...")
search_files("d:\\Internship")
print("Searching brain directory...")
search_files(r"C:\Users\parth\.gemini\antigravity\brain")
