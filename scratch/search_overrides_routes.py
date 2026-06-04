import os

def search_in_files(keyword, dir_path):
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            if file.endswith((".py", ".js", ".html")):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if keyword in line:
                                print(f"{file_path}:{line_num}: {line.strip()}")
                except Exception as e:
                    pass

print("Searching for '/api/' routes in serve.py:")
search_in_files("/api/", "dashboard")
print("\nSearching for 'overrides' in dashboard:")
search_in_files("overrides", "dashboard")
print("\nSearching for 'overrides' in src:")
search_in_files("overrides", "src")
