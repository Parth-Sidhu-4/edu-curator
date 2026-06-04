import urllib.request
import hashlib
import base64

urls = [
    "https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.css",
    "https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.js",
    "https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/contrib/auto-render.min.js",
    "https://cdn.jsdelivr.net/npm/marked/marked.min.js",
    "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2",
    "https://unpkg.com/@phosphor-icons/web@2.1.1/src/light/style.css"
]

for url in urls:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as res:
            data = res.read()
            sha = hashlib.sha384(data).digest()
            sri = "sha384-" + base64.b64encode(sha).decode('utf-8')
            print(f"{url} -> {sri}")
    except Exception as e:
        print(f"Error {url}: {e}")
