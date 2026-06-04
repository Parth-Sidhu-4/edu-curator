import socket
import ssl

# Save original getaddrinfo
_original_getaddrinfo = socket.getaddrinfo

# Patched getaddrinfo to map the database host to the pooler's IPv4 address
def custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host == "db.qofphbmnxoorgbhtmmni.supabase.co":
        pooler_host = "aws-0-ap-south-1.pooler.supabase.com"
        print(f"[DNS Patch] Intercepted {host}:{port} -> routing to pooler {pooler_host}:6543")
        return _original_getaddrinfo(pooler_host, 6543, socket.AF_INET, type, proto, flags)
    return _original_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = custom_getaddrinfo

# Monkeypatch SSLContext.wrap_socket to force SNI hostname
_original_wrap_socket = ssl.SSLContext.wrap_socket
def custom_wrap_socket(self, sock, *args, **kwargs):
    print(f"[SSL Patch] wrap_socket called, forcing server_hostname to qofphbmnxoorgbhtmmni.supabase.co")
    kwargs['server_hostname'] = "qofphbmnxoorgbhtmmni.supabase.co"
    return _original_wrap_socket(self, sock, *args, **kwargs)
ssl.SSLContext.wrap_socket = custom_wrap_socket

import pg8000

print("Attempting to connect via pg8000 with socket DNS patch...")
try:
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    conn = pg8000.connect(
        host="db.qofphbmnxoorgbhtmmni.supabase.co",
        port=5432,
        user="postgres",
        password="VincenzoCassano04",
        database="postgres",
        ssl_context=ssl_ctx
    )
    print("CONNECTION SUCCESSFUL!")
    cursor = conn.cursor()
    cursor.execute("SELECT version();")
    print("Version:", cursor.fetchone())
    cursor.execute("SELECT current_user;")
    print("User:", cursor.fetchone())
    conn.close()
except Exception as e:
    print("Connection failed:", e)
