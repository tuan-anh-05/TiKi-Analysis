"""
Build script tạo dashboard_v2.html từ dữ liệu mới nhất (CSV hoặc Supabase).
Chạy bằng Python thuần túy, tương thích hoàn toàn trên Windows, Linux và macOS.

Cách chạy:
    python 05_dashboard/build.py
Thêm cờ --no-open để không tự mở trình duyệt:
    python 05_dashboard/build.py --no-open
"""

import argparse
from pathlib import Path
import subprocess
import sys
import webbrowser


def main():
    parser = argparse.ArgumentParser(description="Tạo dashboard_v2.html từ dữ liệu Tiki Analytics")
    parser.add_argument("--no-open", "-NoOpen", action="store_true", help="Không tự động mở trình duyệt sau khi build")
    args = parser.parse_args()

    dash_dir = Path(__file__).resolve().parent
    env_file = dash_dir / ".env"
    scripts_dir = dash_dir / "scripts"

    if env_file.is_file():
        print("1/2  Đang xuất dữ liệu từ Supabase...")
        py_export = scripts_dir / "export_data_supabase.py"
    else:
        print("1/2  Đang xuất dữ liệu từ CSV (02_process_raw_data)...")
        py_export = scripts_dir / "export_data.py"

    subprocess.run([sys.executable, str(py_export)], check=True)

    print("2/2  Đang ghép dữ liệu vào giao diện...")
    tpl_file = dash_dir / "dashboard_v2_template.html"
    json_file = dash_dir / "data.json"
    out_file = dash_dir / "dashboard_v2.html"

    if not tpl_file.is_file():
        raise FileNotFoundError(f"Không tìm thấy template: {tpl_file}")
    if not json_file.is_file():
        raise FileNotFoundError(f"Không tìm thấy data.json: {json_file}")

    tpl_content = tpl_file.read_text(encoding="utf-8")
    json_content = json_file.read_text(encoding="utf-8").replace("</", "<\\/")

    final_html = tpl_content.replace("__DATA__", json_content)
    out_file.write_text(final_html, encoding="utf-8")

    size_mb = out_file.stat().st_size / (1024 * 1024)
    print(f"\n✓ Xong: {out_file} ({size_mb:.2f} MB)")

    if not args.no_open:
        print("Đang mở dashboard trong trình duyệt...")
        webbrowser.open(out_file.as_uri())


if __name__ == "__main__":
    main()
