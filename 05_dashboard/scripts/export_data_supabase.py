"""
Xuất dữ liệu cho Dashboard từ Supabase PostgREST API bằng Python thuần túy.
Thay thế export_data_supabase.ps1 và supabase_client.ps1.
"""

from datetime import datetime, timedelta
from pathlib import Path
import json
import os
import re
import subprocess
import sys
import time
import requests


def read_dotenv(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy {path}. Sao chép .env.example thành .env và điền SUPABASE_URL, SUPABASE_KEY.")
    cfg = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, val = line.partition("=")
        if sep:
            cfg[key.strip()] = val.strip().strip("\"'")
    for k in ["SUPABASE_URL", "SUPABASE_KEY"]:
        if not cfg.get(k):
            raise ValueError(f"Thiếu {k} trong {path}")
    return cfg


def get_supabase_rows(cfg: dict, table: str, query: str, page_size: int = 1000) -> list:
    base_url = cfg["SUPABASE_URL"].rstrip("/") + f"/rest/v1/{table}?{query}"
    headers = {
        "apikey": cfg["SUPABASE_KEY"],
        "Prefer": "count=exact",
    }
    rows = []
    offset = 0
    total = None

    while True:
        url = f"{base_url}&limit={page_size}&offset={offset}"
        resp = None
        for attempt in range(1, 4):
            try:
                resp = requests.get(url, headers=headers, timeout=120)
                resp.raise_for_status()
                break
            except Exception as e:
                if attempt >= 3:
                    raise RuntimeError(f"Lỗi khi tải bảng '{table}' từ Supabase: {e}")
                time.sleep(2 * attempt)

        page = resp.json()
        n = len(page)
        if n > 0:
            rows.extend(page)

        cr = resp.headers.get("Content-Range", "")
        m = re.search(r"/(\d+)$", cr)
        if m:
            total = int(m.group(1))

        offset += n
        if n == 0 or (total is not None and offset >= total):
            break

    if total is not None and len(rows) != total:
        print(f"[CẢNH BÁO] '{table}': nhận {len(rows)} dòng nhưng server báo tổng {total}")
    return rows


def export_data_supabase():
    t0 = time.time()
    dash_dir = Path(__file__).resolve().parents[1]
    env_file = dash_dir / ".env"
    cfg = read_dotenv(env_file)
    out_file = dash_dir / "data.json"

    d_from = cfg.get("DAILY_FROM") or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    d_to = cfg.get("DAILY_TO") or datetime.now().strftime("%Y-%m-%d")

    print("[Supabase] 1. Đang tải dữ liệu sản phẩm (vw_dash_product)...")
    prod = get_supabase_rows(cfg, "vw_dash_product", "select=*&order=product_id")

    cats, cat_idx = [], {}
    brands, brand_idx = [], {}
    p_flat = []
    names = []
    pid_idx = {}

    for i, r in enumerate(prod):
        cid = str(r["category_id"]) if r.get("category_id") is not None else ""
        if cid not in cat_idx:
            cat_idx[cid] = len(cats)
            cats.append(r.get("category_name") or "")

        b = str(r.get("brand_name") or "").strip() or "OEM"
        if b not in brand_idx:
            brand_idx[b] = len(brands)
            brands.append(b)

        sold = float(r.get("all_time_quantity_sold") or 0)
        rc = float(r.get("review_count") or 0)
        ra = float(r.get("rating_average") or 0.0)

        p_flat.extend([
            cat_idx[cid],
            int(r.get("seller_group") or 2),
            round(float(r.get("seller_price") or -1)),
            sold,
            round(ra, 1),
            int(rc),
            brand_idx[b],
            int(r.get("created_year") or 0),
        ])

        nm = str(r.get("product_name") or "")
        if len(nm) > 90:
            nm = nm[:88] + "…"
        names.append(nm if (sold > 0 or rc > 0) else "")

        pid_idx[str(r["product_id"])] = i

    print("[Supabase] 2. Đang tải chuỗi giá theo ngày (mv_dash_daily_series)...")
    dy_flat = []
    dy_products = 0
    dd_json = None
    use_series = False

    try:
        ser = get_supabase_rows(cfg, "mv_dash_daily_series", "select=product_id,d0,nd,series&order=product_id")
        n_days = 0
        d0 = ""
        for r in ser:
            pk = str(r["product_id"])
            if pk not in pid_idx:
                continue
            n_days = int(r["nd"])
            d0 = str(r["d0"])
            series_tokens = [int(x) for x in str(r["series"]).split(",") if x.strip()]
            if len(series_tokens) != n_days:
                raise ValueError(f"Chuỗi của sản phẩm {pk} không đủ {n_days} ngày")
            dy_flat.append(pid_idx[pk])
            dy_flat.extend(series_tokens)
            dy_products += 1

        if dy_products > 0:
            dd_json = {"d0": d0[:10], "n": n_days}
            use_series = True
    except Exception as e:
        print(f"[CẢNH BÁO] Bỏ qua chuỗi giá theo ngày từ Supabase: {e}")

    # Fallback cửa sổ cố định nếu không có series
    d_flat = []
    seen_daily = set()
    if not use_series:
        print("[Supabase] 3. Tải dữ liệu giá cố định (vw_daily_price_analysis)...")
        daily = get_supabase_rows(
            cfg,
            "vw_daily_price_analysis",
            f"select=product_id,seller_product_id,category_id,crawl_date,discount_rate,all_time_quantity_sold,inventory_status&crawl_date=in.({d_from},{d_to})&order=id"
        )
        a, z = {}, {}
        for r in daily:
            k = f"{r['product_id']}_{r['seller_product_id']}"
            if r["crawl_date"] == d_from:
                a[k] = r
            elif r["crawl_date"] == d_to:
                z[k] = r

        for k in sorted(z.keys()):
            r = z[k]
            pk = str(r["product_id"])
            if pk not in pid_idx or pk in seen_daily:
                continue
            seen_daily.add(pk)
            delta = -1
            if k in a:
                q0 = float(a[k].get("all_time_quantity_sold") or 0)
                q1 = float(r.get("all_time_quantity_sold") or 0)
                if q0 > 0 and q1 >= q0 and (q1 - q0) < 5000:
                    delta = int(q1 - q0)
            oos = 1 if str(r.get("inventory_status") or "").strip().lower() == "out_of_stock" else 0
            disc = round(float(r.get("discount_rate") or 0))
            d_flat.extend([pid_idx[pk], disc, delta, oos])

    print("[Supabase] 4. Đang tải số sao đánh giá (mv_dash_review_stars)...")
    rs_flat = []
    rs_products = 0
    try:
        stars = get_supabase_rows(cfg, "mv_dash_review_stars", "select=product_id,r1,r2,r3,r4,r5&order=product_id")
        for r in stars:
            pk = str(r["product_id"])
            if pk not in pid_idx:
                continue
            rs_flat.extend([
                pid_idx[pk],
                int(r.get("r1") or 0),
                int(r.get("r2") or 0),
                int(r.get("r3") or 0),
                int(r.get("r4") or 0),
                int(r.get("r5") or 0),
            ])
            rs_products += 1
    except Exception as e:
        print(f"[CẢNH BÁO] Không tải được review stars: {e}")

    print("[Supabase] 5. Đang tải khía cạnh phàn nàn (mv_dash_review_aspect)...")
    asp_flat = []
    asp_products = 0
    try:
        asp = get_supabase_rows(cfg, "mv_dash_review_aspect", "select=product_id,neg_total,a1,a2,a3,a4,a5,a6,a7&order=product_id")
        for r in asp:
            pk = str(r["product_id"])
            if pk not in pid_idx:
                continue
            asp_flat.extend([
                pid_idx[pk],
                int(r.get("neg_total") or 0),
                int(r.get("a1") or 0),
                int(r.get("a2") or 0),
                int(r.get("a3") or 0),
                int(r.get("a4") or 0),
                int(r.get("a5") or 0),
                int(r.get("a6") or 0),
                int(r.get("a7") or 0),
            ])
            asp_products += 1
    except Exception as e:
        print(f"[INFO] Bỏ qua khía cạnh phàn nàn: {e}")

    data = {
        "cats": cats,
        "brands": brands,
        "names": names,
        "p": p_flat,
        "d": d_flat,
        "rs": rs_flat,
        "asp": asp_flat,
        "dd": dd_json,
        "dy": dy_flat,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    file_size_mb = out_file.stat().st_size / (1024 * 1024)
    print(f"\n[SUPABASE HOÀN TẤT] products={len(prod)} cats={len(cats)} brands={len(brands)} daily_series={dy_products} review_stars={rs_products} aspect={asp_products} size={file_size_mb:.2f}MB (trong {time.time()-t0:.2f}s)")


if __name__ == "__main__":
    export_data_supabase()
