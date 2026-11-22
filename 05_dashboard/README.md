# Dashboard Phân Tích Tiki

Dashboard là một trang HTML tĩnh dạng Single Page Application (SPA). Toàn bộ dữ liệu được tổng hợp và nhúng sẵn vào file HTML lúc dựng trang (`build`), do đó người xem chỉ cần mở file bằng bất kỳ trình duyệt nào mà không cần cài đặt web server hay backend.

---

## 1. Yêu cầu hệ thống
- **Hệ điều hành:** Windows 10/11 với PowerShell 5.1 trở lên.
- **Python 3.x + pandas** (tuỳ chọn nhưng khuyến nghị): Dùng để tự động trích xuất phân bố số sao đánh giá (`review_stars.csv`) từ dữ liệu review thô khi chạy chế độ CSV.

---

## 2. Cách chạy và dựng Dashboard

Hệ thống hỗ trợ **2 chế độ chạy** thông qua một lệnh duy nhất:

```powershell
# Chạy trong PowerShell tại thư mục 05_dashboard:
powershell -ExecutionPolicy Bypass -File .\build.ps1
```
> Hoặc nhấp chuột phải vào file `build.ps1` chọn **"Run with PowerShell"**.

### Chế độ A: Dùng dữ liệu CSV nội bộ (Mặc định khi KHÔNG có file `.env`)
- **Khi nào dùng:** Khi chạy trên máy cá nhân, không có tài khoản/khóa API của Supabase hoặc khi đang phát triển offline.
- **Cơ chế:** `build.ps1` tự động gọi `export_data.ps1` để đọc dữ liệu đã làm sạch từ thư mục `..\02_process_raw_data\`. 
- Tự động trích xuất phân bố đánh giá 1★–5★ nếu có Python + pandas.
- Không cần cấu hình bất kỳ file `.env` nào.

### Chế độ B: Dùng dữ liệu trực tuyến từ Supabase (Khi CÓ file `.env`)
- **Khi nào dùng:** Khi cần đồng bộ dữ liệu mới nhất được nạp tự động qua pipeline Supabase.
- **Các bước thiết lập:**
  1. Sao chép `.env.example` thành `.env`:
     ```env
     SUPABASE_URL=https://<project-ref>.supabase.co
     SUPABASE_KEY=sb_publishable_... (hoặc anon key công khai)
     ```
     *(Lưu ý: Chỉ dùng publishable/anon key, tuyệt đối không dùng secret key hoặc mật khẩu DB).*
  2. Đảm bảo các View và Materialized View trong `supabase_views.sql` đã được chạy trong tab **SQL Editor** của Supabase.
  3. Chạy `.\build.ps1`. Script sẽ gọi `export_data_supabase.ps1` để kéo dữ liệu qua PostgREST API.

Sau khi build xong, chương trình sẽ tự động mở file `dashboard_v2.html` trên trình duyệt mặc định. Thêm tham số `-NoOpen` nếu chạy ngầm không muốn tự bật trình duyệt.

---

## 3. Cấu trúc thư mục

```text
05_dashboard/
├── build.ps1                      # File điều phối chính duy nhất cần chạy
├── dashboard_v2_template.html     # Khung mẫu giao diện HTML
├── dashboard_v2.html              # Thành phẩm sau build (mở xem trực tiếp)
├── README.md                      # Hướng dẫn sử dụng
├── .env.example                   # Mẫu khai báo biến môi trường Supabase
├── .gitignore
│
├── scripts/                       # 📁 Chứa các script trích xuất & xử lý dữ liệu
│   ├── export_data.ps1            # Trích xuất dữ liệu từ các file CSV local
│   ├── export_daily_series.py     # Trích xuất & mã hóa chuỗi thời gian theo ngày (tự động cập nhật)
│   ├── export_data_supabase.ps1   # Trích xuất từ Supabase REST API
│   ├── supabase_client.ps1        # Module hỗ trợ kết nối REST API Supabase
│   └── update_dashboard.ps1       # Script cập nhật tự động định kỳ
│
└── sql/                           # 📁 Chứa các script SQL cho Supabase
    ├── supabase_views.sql         # Tạo View và Materialized View
    └── supabase_schedule_refresh.sql # Lịch tự động làm mới view
```

---

## 4. Tự động hóa cập nhật Dashboard

### Cách 1: Tự động qua GitHub Actions & GitHub Pages
Workflow tự động đã được đặt tại `.github/workflows/dashboard.yml`.
1. Vào GitHub Repository → **Settings** → **Secrets and variables** → **Actions**, thêm 2 secrets:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
2. Vào **Settings** → **Pages** → Source chọn **GitHub Actions**.
3. Hằng ngày lúc 23:00 (giờ VN), GitHub sẽ tự build lại dashboard từ Supabase và xuất bản lên GitHub Pages.

### Cách 2: Tự động trên máy local qua Task Scheduler
- Bạn có thể đặt lịch Windows Task Scheduler chạy file `scripts\update_dashboard.ps1`.
- Script này có cơ chế tự động thử lại tối đa 4 lần (mỗi lần cách nhau 5 phút) đề phòng mất mạng tạm thời.

---

## 5. Lưu ý & Bảo mật
- **Bảo mật:** Không bao giờ commit file `.env` lên GitHub (đã được cấu hình trong `.gitignore`).
- **File sinh tự động:** `data.json` và `dashboard_v2.html` là kết quả build, không cần đưa lên kho mã nguồn.
- **Làm mới dữ liệu Supabase:** Nếu vừa nạp dữ liệu thô mới vào Supabase, hãy chạy lệnh sau trong SQL Editor trước khi build:
  ```sql
  REFRESH MATERIALIZED VIEW public.mv_dash_review_stars;
  REFRESH MATERIALIZED VIEW public.mv_dash_review_aspect;
  REFRESH MATERIALIZED VIEW public.mv_dash_daily_series;
  ```
