import urllib.request
import json

# Try freeipapi.com which is public and open
url = "https://freeipapi.com/api/json/2406:da1a:b00:1301:b7e0:af79:530b:ec9c"
try:
    print("Querying freeipapi.com for IPv6 location...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode('utf-8'))
        print(json.dumps(data, indent=2))
except Exception as e:
    print("Query failed:", e)
