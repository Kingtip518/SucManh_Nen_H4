# Bàn Ghép Cặp H4 – Hướng dẫn cài đặt

Công cụ tự chạy trên GitHub, máy tính của anh tắt vẫn chạy:

- **Mỗi giờ:** lấy nến 28 cặp, tính sức mạnh tiền tệ trong ngày, tìm mô hình nến 4 giờ đảo chiều, cập nhật trang web.
- **Khi có nến 4 giờ mới đóng:** gửi báo cáo về Telegram, kèm đường dẫn trang web.

## Bước 1. Tạo bot Telegram (5 phút)

1. Mở Telegram, tìm **@BotFather**, gõ `/newbot`, đặt tên bot (ví dụ `TuGhepCapH4_bot`).
2. BotFather trả về **mã bot**, dạng `123456789:AAH...`. Chép lại, không gửi cho ai.
3. Mở bot vừa tạo, bấm **Bắt đầu** (Start), gõ một tin bất kỳ.
4. Lấy **mã chat** của anh: tìm **@userinfobot**, bấm Start. Dòng `Id` là mã chat (một dãy số).

## Bước 2. Tạo kho trên GitHub (tài khoản Kingtip518)

1. Vào github.com, bấm **New repository**, đặt tên `SucManh_Nen_H4`, chọn **Public**, bấm **Create**.
2. Bấm **uploading an existing file**, kéo toàn bộ file trong thư mục giải nén vào, gồm cả thư mục `.github`. Bấm **Commit changes**.
   - Máy Windows hay ẩn thư mục `.github`. Nếu không kéo được, trên GitHub bấm **Add file → Create new file**, gõ tên `.github/workflows/phan-tich.yml`, dán nội dung file đó vào.

## Bước 3. Cất mã Telegram vào kho (bí mật, không ai xem được)

Vào **Settings → Secrets and variables → Actions → New repository secret**, tạo 2 mục:

| Tên | Giá trị |
|---|---|
| `TELEGRAM_TOKEN` | Mã bot ở bước 1 |
| `TELEGRAM_CHAT_ID` | Mã chat ở bước 1 |

## Bước 4. Bật trang web

**Settings → Pages → Source: Deploy from a branch → Branch: main, thư mục / (root) → Save.**

Sau 1–2 phút trang có ở: `https://kingtip518.github.io/SucManh_Nen_H4/`

## Bước 5. Chạy thử lần đầu

1. Vào tab **Actions**, nếu GitHub hỏi thì bấm bật quy trình.
2. Chọn **Quet nen 4 gio va suc manh tien te → Run workflow → Run workflow**.
3. Khoảng 1 phút sau, Telegram nhận báo cáo và trang web hiện dữ liệu thật.

Từ đó công cụ tự chạy mỗi giờ (phút thứ 7), nghỉ thứ Bảy. Muốn nhận báo cáo ngay lúc bất kỳ, làm lại bước 5.

## Điều chỉnh

Các con số cài đặt nằm ở đầu file `phan_tich.py`:

| Cài đặt | Mặc định | Ý nghĩa |
|---|---|---|
| `SO_NEN_XET_DINH_DAY` | 12 | Mô hình phải nằm ở đỉnh hoặc đáy của bao nhiêu nến 4 giờ |
| `SO_NEN_GAN_NHAT_XET` | 3 | Xét mô hình trong bao nhiêu nến 4 giờ vừa đóng |
| `CHENH_LECH_TOI_THIEU` | 0.15 | Chênh lệch sức mạnh tối thiểu giữa hai đồng (%) |
| `SO_NEN_TIM_MUC_TIEU` | 20 | Mục tiêu là đỉnh hoặc đáy của bao nhiêu nến 4 giờ gần nhất |

## Lưu ý

- Nến lấy từ Yahoo Finance, gộp theo giờ sàn MT5 phổ biến (0 giờ sàn = 17 giờ New York, giống Global Prime). Giá có thể lệch vài pip so với MT5 của anh.
- GitHub đôi khi chạy trễ 5–15 phút so với lịch.
- Đây là công cụ tham khảo, không phải lời khuyên đầu tư.
