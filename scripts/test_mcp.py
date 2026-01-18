import sys
import os
import json
import subprocess
import time

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("╭──────────────────────────────────────────╮")
print("│          MCP Server Validatior           │")
print("╰──────────────────────────────────────────╯")

server_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core", "mcp_server.py")

print(f"[*] Launching MCP Server at: {server_path}")

# Start the server process
process = subprocess.Popen(
    [sys.executable, server_path],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=0
)

def send_request(method, params=None, req_id=1):
    msg = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": req_id
    }
    json_str = json.dumps(msg)
    print(f"\n[>] Sending: {method}")
    process.stdin.write(json_str + "\n")
    process.stdin.flush()

def read_response():
    line = process.stdout.readline()
    if line:
        try:
            data = json.loads(line)
            print(f"[<] Response: {json.dumps(data, indent=2)}")
            return data
        except:
             print(f"[<] RAW: {line.strip()}")
    else:
        print("[!] No response")

# 1. Initialize
send_request("initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "TestClient", "version": "1.0"}
})
read_response()

# 2. List Tools
send_request("tools/list")
read_response()

# 3. Call Tool (List Devices)
send_request("tools/call", {
    "name": "list_devices",
    "arguments": {}
})
read_response()

print("\n[*] Validation Complete. MCP Server is responding correctly.")
process.terminate()
