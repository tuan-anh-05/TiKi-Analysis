"""
Module quản lý Proxy và Tự động xoay IP cho các crawler Tiki.

- Hỗ trợ Cloudflare WARP SOCKS5 proxy qua biến môi trường WARP_PROXY_URL.
- Tự động gọi API xoay IP (POST /rotate) qua WARP_CONTROL_URL khi gặp HTTP 429/403.
- Cơ chế Thread-safe và Debounce (chống xoay IP dồn dập khi nhiều luồng cùng gặp lỗi).
- Tương thích ngược: Nếu không chạy Docker hoặc không có WARP, script vẫn chạy bình thường.
"""

from __future__ import annotations

import os
import time
import threading
import requests

WARP_PROXY_URL = os.environ.get("WARP_PROXY_URL")
WARP_CONTROL_URL = os.environ.get("WARP_CONTROL_URL")

_rotate_lock = threading.Lock()
_last_rotate_time = 0.0
_COOLDOWN_SECONDS = 5.0


def is_warp_enabled() -> bool:
    """Kiểm tra xem cấu hình WARP proxy có được bật hay không."""
    return bool(WARP_PROXY_URL)


def get_proxy_dict() -> dict[str, str] | None:
    """Trả về dictionary proxies cho thư viện requests nếu có cấu hình."""
    if WARP_PROXY_URL:
        return {
            "http": WARP_PROXY_URL,
            "https": WARP_PROXY_URL,
        }
    return None


def configure_session(session: requests.Session) -> requests.Session:
    """Gắn WARP proxy vào requests.Session nếu được kích hoạt."""
    proxies = get_proxy_dict()
    if proxies:
        session.proxies.update(proxies)
    return session


def get_current_ip() -> str | None:
    """Lấy địa chỉ IP hiện tại từ WARP control API hoặc thông qua proxy."""
    if WARP_CONTROL_URL:
        try:
            resp = requests.get(f"{WARP_CONTROL_URL}/ip", timeout=5)
            if resp.status_code == 200:
                return resp.json().get("ip")
        except Exception:
            pass

    try:
        session = configure_session(requests.Session())
        resp = session.get("https://api.ipify.org?format=json", timeout=5)
        if resp.status_code == 200:
            return resp.json().get("ip")
    except Exception:
        pass

    return None


def rotate_ip(force_reset: bool = False, delay: float = 3.0) -> str | None:
    """
    Kích hoạt đổi IP mới từ Cloudflare WARP.
    Thread-safe và có cooldown 5s để tránh xoay liên tiếp khi nhiều worker cùng lỗi.
    """
    global _last_rotate_time

    if not WARP_CONTROL_URL:
        # Nếu không có WARP control API (chạy local ngoài Docker), chỉ sleep chờ rate-limit
        time.sleep(delay)
        return None

    with _rotate_lock:
        now = time.time()
        # Nếu vừa mới xoay IP trong vòng 5 giây trước đó (do luồng khác gọi), không xoay lại
        if now - _last_rotate_time < _COOLDOWN_SECONDS:
            time.sleep(delay)
            return get_current_ip()

        endpoint = f"{WARP_CONTROL_URL}/reset" if force_reset else f"{WARP_CONTROL_URL}/rotate"
        try:
            print("[WARP] 🔄 Đang gửi yêu cầu đổi IP mới tới WARP container...")
            resp = requests.post(endpoint, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                new_ip = data.get("new_ip")
                old_ip = data.get("old_ip")
                print(f"[WARP] ✅ Đổi IP thành công: {old_ip} -> {new_ip}")
                _last_rotate_time = time.time()
                time.sleep(delay)
                return new_ip
            else:
                print(f"[WARP] ⚠️ Lỗi khi gọi đổi IP: HTTP {resp.status_code}")
        except Exception as exc:
            print(f"[WARP] ⚠️ Không thể kết nối tới WARP Control API: {exc}")

        _last_rotate_time = time.time()
        time.sleep(delay)
        return None
