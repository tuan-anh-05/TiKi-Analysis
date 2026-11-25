import os
import sys
import json
import time
import pandas as pd

def main():
    t0 = time.time()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dash_dir = os.path.dirname(script_dir)
    base = os.path.abspath(os.path.join(dash_dir, "..", "02_process_raw_data"))
    data_path = os.path.join(dash_dir, "data.json")

    if not os.path.exists(data_path):
        print(f"Không tìm thấy {data_path}")
        return

    prod_csv = os.path.join(base, "product", "product.csv")
    detail_csv = os.path.join(base, "product", "product_detail.csv")
    daily_csv = os.path.join(base, "daily_price", "daily_price_history.csv")

    for path in [prod_csv, detail_csv, daily_csv]:
        if not os.path.exists(path):
            print(f"Không tìm thấy file {path}")
            return

    # 1. Map product_id -> category_id
    df_p = pd.read_csv(prod_csv, usecols=["product_id", "category_id"])
    prod_cat = {}
    for _, row in df_p.iterrows():
        pid = str(int(row["product_id"])) if pd.notnull(row["product_id"]) else ""
        if pid and pid not in prod_cat:
            prod_cat[pid] = str(int(row["category_id"])) if pd.notnull(row["category_id"]) else ""

    # 2. product_detail -> pid_list (thứ tự chỉ số trong RAW.p)
    pid_list = []
    seen = set()
    df_pd = pd.read_csv(detail_csv, usecols=["product_id"])
    for pid_val in df_pd["product_id"].dropna():
        pid = str(int(pid_val))
        cid = prod_cat.get(pid)
        if not cid:
            continue
        if pid in seen:
            continue
        seen.add(pid)
        pid_list.append(pid)

    pid_to_idx = {pid: i for i, pid in enumerate(pid_list)}

    # 3. Đọc dữ liệu daily_price_history
    df_d = pd.read_csv(daily_csv, usecols=[
        "product_id", "seller_product_id", "category_id", "crawl_date",
        "discount_rate", "all_time_quantity_sold", "inventory_status"
    ])
    df_d["product_id"] = df_d["product_id"].dropna().astype(int).astype(str)
    df_d = df_d[df_d["product_id"].isin(pid_to_idx)]

    dates = sorted(df_d["crawl_date"].dropna().unique())
    if not dates:
        print("Không tìm thấy ngày trong dữ liệu giá hằng ngày.")
        return

    d0 = str(dates[0])
    n_days = len(dates)
    date_to_idx = {d: i for i, d in enumerate(dates)}

    # Với mỗi sản phẩm và ngày, chọn seller_product_id nhỏ nhất
    df_d = df_d.sort_values(["product_id", "seller_product_id", "crawl_date"])
    df_d = df_d.drop_duplicates(subset=["product_id", "crawl_date"], keep="first")

    records = {}
    for _, row in df_d.iterrows():
        pid = row["product_id"]
        if pid not in records:
            records[pid] = {}
        d_idx = date_to_idx[row["crawl_date"]]
        disc = int(min(max(round(row["discount_rate"]), 0), 100)) if pd.notnull(row["discount_rate"]) else 0
        qty = float(row["all_time_quantity_sold"]) if pd.notnull(row["all_time_quantity_sold"]) else 0.0
        oos = 1 if str(row["inventory_status"]).strip().lower() == "out_of_stock" else 0
        records[pid][d_idx] = (disc, qty, oos)

    dy_list = []
    dy_products = 0
    for pid in pid_list:
        if pid not in records:
            continue
        rec = records[pid]
        dy_list.append(pid_to_idx[pid])
        dy_products += 1
        for t in range(n_days):
            if t not in rec:
                dy_list.append(-1)
                continue
            disc, qty, oos = rec[t]
            enc = 0
            if t >= 1 and (t - 1) in rec:
                p_disc, p_qty, p_oos = rec[t - 1]
                if p_qty > 0 and qty >= p_qty and (qty - p_qty) < 5000:
                    enc = int(qty - p_qty) + 1
            v = (((enc * 101) + disc) * 2) + oos
            dy_list.append(v)

    # Đọc data.json hiện tại và nạp dd + dy vào
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["dd"] = {"d0": d0, "n": n_days}
    data["dy"] = dy_list

    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    print(f"[Chuỗi ngày] Đã nạp thành công: {d0} -> {dates[-1]} ({n_days} ngày), {dy_products} sản phẩm theo dõi trong {time.time()-t0:.2f}s")

if __name__ == "__main__":
    main()
