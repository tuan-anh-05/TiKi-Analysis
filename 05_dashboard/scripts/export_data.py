"""
Xuất dữ liệu gọn để nhúng vào dashboard_v2.html từ nguồn dữ liệu CSV (02_process_raw_data).
Thay thế hoàn toàn export_data.ps1 bằng Python thuần túy, tương thích 100% mọi hệ điều hành.
"""

from pathlib import Path
import json
import re
import subprocess
import sys
import time
import pandas as pd


def export_data():
    t0 = time.time()
    dash_dir = Path(__file__).resolve().parents[1]
    root_dir = dash_dir.parent
    base_dir = root_dir / "02_process_raw_data"
    out_file = dash_dir / "data.json"

    print("1. Đang nạp danh mục và phân loại sản phẩm...")
    # Danh mục
    cat_df = pd.read_csv(base_dir / "category" / "category.csv", usecols=["category_id", "name"], low_memory=False)
    cat_name = dict(zip(cat_df["category_id"].astype(str), cat_df["name"]))

    # Product -> Category
    prod_df = pd.read_csv(base_dir / "product" / "product.csv", usecols=["product_id", "category_id"], low_memory=False)
    prod_df = prod_df.dropna(subset=["product_id", "category_id"]).drop_duplicates(subset=["product_id"], keep="first")
    prod_cat = dict(zip(prod_df["product_id"].astype(int).astype(str), prod_df["category_id"].astype(int).astype(str)))

    print("2. Đang nạp thông tin người bán...")
    # Người bán hiện tại
    seller_file = base_dir / "product" / "product_seller.csv"
    seller_dict = {}
    if seller_file.exists():
        seller_df = pd.read_csv(seller_file, low_memory=False)
        seller_df = seller_df[seller_df["is_current_seller"].astype(str).str.lower().isin(["true", "1"])]
        seller_df = seller_df.drop_duplicates(subset=["product_id"], keep="first")
        for _, r in seller_df.iterrows():
            pid = str(int(r["product_id"])) if pd.notnull(r["product_id"]) else ""
            if not pid:
                continue
            sid = str(int(r["seller_id"])) if pd.notnull(r["seller_id"]) else ""
            sname = str(r["seller_name"]) if pd.notnull(r["seller_name"]) else ""
            if sid == "1":
                g = 0
            elif re.search(r"(?i)(official|chính hãng|chinh hang|flagship)", sname):
                g = 1
            else:
                g = 2
            price = round(float(r["seller_price"])) if pd.notnull(r["seller_price"]) else -1
            seller_dict[pid] = (g, price)

    print("3. Đang xử lý danh mục sản phẩm chi tiết...")
    detail_df = pd.read_csv(base_dir / "product" / "product_detail.csv", low_memory=False)
    cats = []
    cat_idx = {}
    brands = []
    brand_idx = {}
    names = []
    p_flat = []
    pid_idx = {}

    idx_counter = 0
    for _, r in detail_df.iterrows():
        if pd.isnull(r["product_id"]):
            continue
        pid = str(int(r["product_id"]))
        cid = prod_cat.get(pid)
        if not cid or pid in pid_idx:
            continue

        if cid not in cat_idx:
            cat_idx[cid] = len(cats)
            cats.append(cat_name.get(cid, ""))

        b = str(r["brand_name"]).strip() if pd.notnull(r["brand_name"]) and str(r["brand_name"]).strip() else "OEM"
        if b not in brand_idx:
            brand_idx[b] = len(brands)
            brands.append(b)

        s_info = seller_dict.get(pid, (2, -1))
        g, price = s_info

        sold = float(r["all_time_quantity_sold"]) if pd.notnull(r["all_time_quantity_sold"]) else 0.0
        rc = float(r["review_count"]) if pd.notnull(r["review_count"]) else 0.0
        ra = float(r["rating_average"]) if pd.notnull(r["rating_average"]) else 0.0
        
        cdate = str(r["created_date"]) if pd.notnull(r["created_date"]) else ""
        m_year = re.match(r"^(\d{4})", cdate)
        year = int(m_year.group(1)) if m_year else 0

        p_flat.extend([
            cat_idx[cid],
            g,
            price,
            sold,
            round(ra, 1),
            int(rc),
            brand_idx[b],
            year
        ])

        nm = str(r["product_name"]) if pd.notnull(r["product_name"]) else ""
        if len(nm) > 90:
            nm = nm[:88] + "…"
        names.append(nm if (sold > 0 or rc > 0) else "")

        pid_idx[pid] = idx_counter
        idx_counter += 1

    print("4. Đang xử lý giá hằng ngày (cửa sổ đầu - cuối)...")
    daily_file = base_dir / "daily_price" / "daily_price_history.csv"
    d_flat = []
    seen_daily = set()
    d_first, d_latest = "", ""

    if daily_file.exists():
        daily_df = pd.read_csv(daily_file, usecols=[
            "product_id", "seller_product_id", "crawl_date",
            "discount_rate", "all_time_quantity_sold", "inventory_status"
        ], low_memory=False)

        dates = sorted(daily_df["crawl_date"].dropna().unique())
        if dates:
            d_first = str(dates[0])
            d_latest = str(dates[-1])

            first_df = daily_df[daily_df["crawl_date"] == d_first].drop_duplicates(
                subset=["product_id", "seller_product_id"], keep="first"
            )
            latest_df = daily_df[daily_df["crawl_date"] == d_latest].drop_duplicates(
                subset=["product_id", "seller_product_id"], keep="first"
            )

            a_map = {
                f"{int(r.product_id)}_{int(r.seller_product_id)}": float(r.all_time_quantity_sold) if pd.notnull(r.all_time_quantity_sold) else 0.0
                for r in first_df.itertuples(index=False) if pd.notnull(r.product_id) and pd.notnull(r.seller_product_id)
            }

            for r in latest_df.itertuples(index=False):
                if pd.isnull(r.product_id) or pd.isnull(r.seller_product_id):
                    continue
                pid = str(int(r.product_id))
                if pid not in pid_idx or pid in seen_daily:
                    continue
                seen_daily.add(pid)

                k = f"{int(r.product_id)}_{int(r.seller_product_id)}"
                delta = -1
                if k in a_map:
                    q0 = a_map[k]
                    q1 = float(r.all_time_quantity_sold) if pd.notnull(r.all_time_quantity_sold) else 0.0
                    if q0 > 0 and q1 >= q0 and (q1 - q0) < 5000:
                        delta = int(q1 - q0)

                oos = 1 if str(r.inventory_status).strip().lower() == "out_of_stock" else 0
                disc = round(float(r.discount_rate)) if pd.notnull(r.discount_rate) else 0

                d_flat.extend([pid_idx[pid], disc, delta, oos])

    print("5. Đang xử lý phân bố đánh giá (review stars)...")
    rs_flat = []
    rs_file = dash_dir / "review_stars.csv"
    if not rs_file.exists():
        rev_csv = base_dir / "review" / "product_review.csv"
        if rev_csv.exists():
            print("  -> Tự động trích xuất review_stars.csv từ dữ liệu review...")
            rev_df = pd.read_csv(rev_csv, usecols=["review_id", "product_id", "rating"], low_memory=False)
            rev_df = rev_df.dropna(subset=["product_id", "rating"]).drop_duplicates(subset=["review_id", "product_id"])
            stars = rev_df.groupby(["product_id", "rating"]).size().reset_index(name="n")
            stars.to_csv(rs_file, index=False)

    rs_products = 0
    if rs_file.exists():
        stars_df = pd.read_csv(rs_file, low_memory=False)
        acc = {}
        for _, r in stars_df.iterrows():
            if pd.isnull(r["product_id"]) or pd.isnull(r["rating"]):
                continue
            pid = str(int(r["product_id"]))
            if pid not in pid_idx:
                continue
            k = int(r["rating"])
            if k < 1 or k > 5:
                continue
            idx = pid_idx[pid]
            if idx not in acc:
                acc[idx] = [0, 0, 0, 0, 0]
            acc[idx][k - 1] += int(r["n"]) if pd.notnull(r["n"]) else 0

        for idx, counts in acc.items():
            rs_flat.extend([idx, counts[0], counts[1], counts[2], counts[3], counts[4]])
        rs_products = len(acc)

    # Đóng gói data.json
    data = {
        "cats": cats,
        "brands": brands,
        "names": names,
        "p": p_flat,
        "d": d_flat,
        "rs": rs_flat,
    }

    print(f"6. Đang ghi dữ liệu vào: {out_file}...")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    # Tự động nạp thêm chuỗi thời gian nếu export_daily_series.py tồn tại
    py_daily = dash_dir / "scripts" / "export_daily_series.py"
    if py_daily.exists():
        print(f"7. Đang cập nhật chuỗi thời gian theo ngày ({d_first} -> {d_latest})...")
        subprocess.run([sys.executable, str(py_daily)], check=True)

    file_size_mb = out_file.stat().st_size / (1024 * 1024)
    print(f"\n[HOÀN TẤT] products={idx_counter} cats={len(cats)} brands={len(brands)} daily={len(seen_daily)} review_stars={rs_products} size={file_size_mb:.2f}MB (trong {time.time()-t0:.2f}s)")


if __name__ == "__main__":
    export_data()
