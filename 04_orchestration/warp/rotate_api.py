import json
import os
import subprocess
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

WARP_PORT = os.environ.get("WARP_PORT", "1080")
API_PORT = int(os.environ.get("API_PORT", "8000"))

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        return res.returncode == 0, res.stdout.strip()
    except Exception as e:
        return False, str(e)

def get_warp_ip():
    """Lấy IP hiện tại qua SOCKS5 proxy của WARP."""
    try:
        ok, out = run_cmd(["curl", "-x", f"socks5h://127.0.0.1:{WARP_PORT}", "-fsS", "--max-time", "5", "https://api.ipify.org?format=json"])
        if ok and out:
            data = json.loads(out)
            return data.get("ip")
    except Exception:
        pass
    
    try:
        ok, out = run_cmd(["curl", "-x", f"socks5h://127.0.0.1:{WARP_PORT}", "-fsS", "--max-time", "5", "https://1.1.1.1/cdn-cgi/trace"])
        if ok and out:
            for line in out.splitlines():
                if line.startswith("ip="):
                    return line.split("=", 1)[1]
    except Exception:
        pass
    return None

def rotate_connection():
    """Ngắt và kết nối lại WARP để nhận session/IP mới."""
    run_cmd(["warp-cli", "--accept-tos", "disconnect"])
    time.sleep(2)
    run_cmd(["warp-cli", "--accept-tos", "connect"])
    
    for _ in range(10):
        time.sleep(1)
        ok, status = run_cmd(["warp-cli", "--accept-tos", "status"])
        if "Connected" in status:
            break
            
    return get_warp_ip()

def reset_registration():
    """Xóa đăng ký cũ và đăng ký tài khoản WARP mới để chắc chắn đổi IP."""
    run_cmd(["warp-cli", "--accept-tos", "disconnect"])
    run_cmd(["warp-cli", "--accept-tos", "registration", "delete"])
    time.sleep(1)
    run_cmd(["warp-cli", "--accept-tos", "registration", "new"])
    run_cmd(["warp-cli", "--accept-tos", "mode", "proxy"])
    run_cmd(["warp-cli", "--accept-tos", "proxy", "port", str(WARP_PORT)])
    run_cmd(["warp-cli", "--accept-tos", "connect"])
    
    for _ in range(10):
        time.sleep(1)
        ok, status = run_cmd(["warp-cli", "--accept-tos", "status"])
        if "Connected" in status:
            break
            
    return get_warp_ip()

class RequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_GET(self):
        if self.path in ("/status", "/health", "/ip"):
            ip = get_warp_ip()
            ok, status = run_cmd(["warp-cli", "--accept-tos", "status"])
            self._send_json(200, {
                "status": "connected" if "Connected" in status else "disconnected",
                "ip": ip,
                "proxy_port": WARP_PORT
            })
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        if self.path == "/rotate":
            old_ip = get_warp_ip()
            new_ip = rotate_connection()
            if new_ip == old_ip and old_ip is not None:
                new_ip = reset_registration()
            self._send_json(200, {
                "message": "Rotated successfully",
                "old_ip": old_ip,
                "new_ip": new_ip
            })
        elif self.path == "/reset":
            old_ip = get_warp_ip()
            new_ip = reset_registration()
            self._send_json(200, {
                "message": "Registration reset successfully",
                "old_ip": old_ip,
                "new_ip": new_ip
            })
        else:
            self._send_json(404, {"error": "Not Found"})

    def log_message(self, format, *args):
        print(f"[ROTATE-API] {self.address_string()} - {format % args}", flush=True)

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", API_PORT), RequestHandler)
    print(f"[ROTATE-API] Server listening on port {API_PORT}...", flush=True)
    server.serve_forever()
