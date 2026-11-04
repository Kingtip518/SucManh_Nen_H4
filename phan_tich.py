#!/usr/bin/env python3
"""
Quét 28 cặp tiền tệ theo phương pháp của Tú Trading Systems:
  Bước 1: tìm mô hình nến đảo chiều trên các nến 4 giờ vừa đóng.
  Bước 2: đối chiếu với sức mạnh tiền tệ trong ngày (giống bảng MarketMilk).
  Bước 3: đề xuất lệnh mua / bán.

Kết quả ghi ra data.json cho trang web đọc.
Khi có nến 4 giờ mới đóng, gửi báo cáo về Telegram.
"""
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# ---------------- Cài đặt (sửa ở đây nếu muốn) ----------------
SO_NEN_XET_DINH_DAY = 12    # Mô hình phải nằm ở đỉnh/đáy của bao nhiêu nến 4 giờ gần nhất
SO_NEN_GAN_NHAT_XET = 3     # Xét mô hình trong bao nhiêu nến 4 giờ vừa đóng
CHENH_LECH_TOI_THIEU = 0.15  # Chênh lệch sức mạnh tối thiểu giữa 2 đồng (đơn vị %)
SO_NEN_TIM_MUC_TIEU = 20    # Mục tiêu = đỉnh/đáy của bao nhiêu nến 4 giờ gần nhất
# ---------------------------------------------------------------

TIEN = ["EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY"]
CAP = [(i, j) for i in range(8) for j in range(i + 1, 8)]   # 28 cặp, tên chuẩn như EURUSD, GBPJPY...
NEW_YORK = ZoneInfo("America/New_York")
GIO_VN = timezone(timedelta(hours=7))
THU_MUC = os.path.dirname(os.path.abspath(__file__))
FILE_DATA = os.path.join(THU_MUC, "data.json")

MA_BOT = os.environ.get("TELEGRAM_TOKEN", "").strip()
MA_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
DIA_CHI_WEB = os.environ.get("DIA_CHI_WEB", "").strip()
LUON_GUI = os.environ.get("LUON_GUI_TELEGRAM", "") == "co"


def lech_gio_san(ts):
    """Số giây giờ sàn lệch so với giờ quốc tế. Sàn MT5 phổ biến (như Global Prime)
    lấy 0 giờ sàn = 17 giờ New York, tức giờ sàn = giờ New York + 7."""
    dt = datetime.fromtimestamp(ts, timezone.utc).astimezone(NEW_YORK)
    return int(dt.utcoffset().total_seconds()) + 7 * 3600


def lay_nen_gio(ten_cap):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ten_cap}=X"
           "?interval=1h&range=1mo")
    for lan in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                kq = json.load(r)["chart"]["result"][0]
            t = kq["timestamp"]
            q = kq["indicators"]["quote"][0]
            nen = []
            for k in range(len(t)):
                if None in (q["open"][k], q["high"][k], q["low"][k], q["close"][k]):
                    continue
                nen.append((t[k], q["open"][k], q["high"][k], q["low"][k], q["close"][k]))
            return nen
        except Exception as loi:
            print(f"Lỗi lấy {ten_cap} lần {lan + 1}: {loi}")
            time.sleep(3)
    return []


def gop_nen_4_gio(nen_gio, bay_gio):
    """Gộp nến 1 giờ thành nến 4 giờ theo giờ sàn. Trả về (nến đã đóng, nến đang chạy)."""
    nhom = {}
    thu_tu = []
    for (t, o, h, l, c) in nen_gio:
        khoa = (t + lech_gio_san(t)) // 14400
        if khoa not in nhom:
            nhom[khoa] = {"t": t, "o": o, "h": h, "l": l, "c": c, "khoa": khoa}
            thu_tu.append(khoa)
        else:
            b = nhom[khoa]
            b["h"] = max(b["h"], h)
            b["l"] = min(b["l"], l)
            b["c"] = c
    nen = [nhom[k] for k in thu_tu]
    khoa_hien_tai = (bay_gio + lech_gio_san(bay_gio)) // 14400
    da_dong = [b for b in nen if b["khoa"] < khoa_hien_tai]
    dang_chay = [b for b in nen if b["khoa"] >= khoa_hien_tai]
    return da_dong, dang_chay


def tinh_atr(nen):
    atr = [0.0] * len(nen)
    a = 0.0
    for i in range(1, len(nen)):
        tr = max(nen[i]["h"] - nen[i]["l"],
                 abs(nen[i]["h"] - nen[i - 1]["c"]),
                 abs(nen[i]["l"] - nen[i - 1]["c"]))
        a = (a * (i - 1) + tr) / i if i <= 14 else (a * 13 + tr) / 14
        atr[i] = a
    return atr


def than(b): return abs(b["c"] - b["o"])
def bien(b): return b["h"] - b["l"]
def rau_tren(b): return b["h"] - max(b["o"], b["c"])
def rau_duoi(b): return min(b["o"], b["c"]) - b["l"]
def tang(b): return b["c"] > b["o"]
def giam(b): return b["c"] < b["o"]


def mo_hinh_tang(n, i, a):
    k, p, pp = n[i], n[i - 1], n[i - 2]
    ds = []
    if giam(p) and tang(k) and k["c"] >= p["o"] and k["o"] <= p["c"] and than(k) > than(p):
        ds.append("nhấn chìm tăng")
    if rau_duoi(k) >= 2 * than(k) and rau_tren(k) <= 0.35 * bien(k) and bien(k) >= 0.8 * a:
        ds.append("búa")
    if giam(pp) and than(pp) > 0.5 * a and than(p) < 0.35 * than(pp) and tang(k) and k["c"] > (pp["o"] + pp["c"]) / 2:
        ds.append("sao mai")
    if giam(p) and tang(k) and abs(k["l"] - p["l"]) < 0.1 * a and than(k) > 0.3 * a:
        ds.append("đáy nhíp")
    if (giam(p) and than(p) > 0.5 * a and tang(k) and k["c"] > (p["o"] + p["c"]) / 2
            and k["c"] < p["o"] and k["o"] <= p["c"] + 0.05 * a):
        ds.append("xuyên đâm")
    return ds


def mo_hinh_giam(n, i, a):
    k, p, pp = n[i], n[i - 1], n[i - 2]
    ds = []
    if tang(p) and giam(k) and k["c"] <= p["o"] and k["o"] >= p["c"] and than(k) > than(p):
        ds.append("nhấn chìm giảm")
    if rau_tren(k) >= 2 * than(k) and rau_duoi(k) <= 0.35 * bien(k) and bien(k) >= 0.8 * a:
        ds.append("sao băng")
    if tang(pp) and than(pp) > 0.5 * a and than(p) < 0.35 * than(pp) and giam(k) and k["c"] < (pp["o"] + pp["c"]) / 2:
        ds.append("sao hôm")
    if tang(p) and giam(k) and abs(k["h"] - p["h"]) < 0.1 * a and than(k) > 0.3 * a:
        ds.append("đỉnh nhíp")
    if (tang(p) and than(p) > 0.5 * a and giam(k) and k["c"] < (p["o"] + p["c"]) / 2
            and k["c"] > p["o"] and k["o"] >= p["c"] - 0.05 * a):
        ds.append("mây đen")
    return ds


def gio_vn(ts):
    return datetime.fromtimestamp(ts, GIO_VN).strftime("%H:%M %d/%m")


def quet_mo_hinh(da_dong, dang_chay, gia):
    """Tìm mô hình gần nhất còn hiệu lực. Trả về dict hoặc None."""
    n = da_dong
    if len(n) < SO_NEN_XET_DINH_DAY + SO_NEN_GAN_NHAT_XET + 20:
        return None
    atr = tinh_atr(n)
    cuoi = len(n) - 1
    for i in range(cuoi, cuoi - SO_NEN_GAN_NHAT_XET, -1):
        a = atr[i]
        if a <= 0:
            continue
        cua_so = n[i - SO_NEN_XET_DINH_DAY:i + 1]
        day_3 = min(n[i]["l"], n[i - 1]["l"], n[i - 2]["l"])
        dinh_3 = max(n[i]["h"], n[i - 1]["h"], n[i - 2]["h"])
        sau = n[i + 1:] + dang_chay

        if day_3 <= min(b["l"] for b in cua_so):
            ds = mo_hinh_tang(n, i, a)
            if ds and gia > day_3 and all(b["l"] > day_3 for b in sau):
                cat_lo = day_3 - 0.1 * a
                muc_tieu = max(b["h"] for b in n[-SO_NEN_TIM_MUC_TIEU:])
                if muc_tieu <= gia:
                    muc_tieu = gia + 2 * (gia - cat_lo)
                return {"huong": 1, "mo_hinh": " + ".join(ds), "gio_nen": gio_vn(n[i]["t"]),
                        "nen_truoc": cuoi - i, "cat_lo": cat_lo, "muc_tieu": muc_tieu}

        if dinh_3 >= max(b["h"] for b in cua_so):
            ds = mo_hinh_giam(n, i, a)
            if ds and gia < dinh_3 and all(b["h"] < dinh_3 for b in sau):
                cat_lo = dinh_3 + 0.1 * a
                muc_tieu = min(b["l"] for b in n[-SO_NEN_TIM_MUC_TIEU:])
                if muc_tieu >= gia:
                    muc_tieu = gia - 2 * (cat_lo - gia)
                return {"huong": -1, "mo_hinh": " + ".join(ds), "gio_nen": gio_vn(n[i]["t"]),
                        "nen_truoc": cuoi - i, "cat_lo": cat_lo, "muc_tieu": muc_tieu}
    return None


def thay_doi_trong_ngay(nen_gio):
    """% thay đổi từ giá mở cửa ngày (theo giờ sàn) tới giá hiện tại."""
    cuoi = nen_gio[-1]
    ngay = (cuoi[0] + lech_gio_san(cuoi[0])) // 86400
    mo = None
    for (t, o, h, l, c) in nen_gio:
        if (t + lech_gio_san(t)) // 86400 == ngay:
            mo = o
            break
    return (cuoi[4] - mo) / mo * 100 if mo else 0.0


def phan_tich(lay_nen=lay_nen_gio, bay_gio=None):
    bay_gio = bay_gio or int(time.time())
    tong = [0.0] * 8
    dem = [0] * 8
    tho = {}
    for (i, j) in CAP:
        ten = TIEN[i] + TIEN[j]
        nen = lay_nen(ten)
        if len(nen) < 100:
            print(f"Thiếu dữ liệu {ten}, bỏ qua")
            continue
        tho[(i, j)] = nen
        pct = thay_doi_trong_ngay(nen)
        tong[i] += pct
        dem[i] += 1
        tong[j] -= pct
        dem[j] += 1
    suc_manh = [tong[c] / dem[c] if dem[c] else 0.0 for c in range(8)]

    dat, loai = [], []
    nen_dong_moi_nhat = 0
    for (i, j), nen in tho.items():
        da_dong, dang_chay = gop_nen_4_gio(nen, bay_gio)
        if da_dong:
            nen_dong_moi_nhat = max(nen_dong_moi_nhat, da_dong[-1]["t"])
        gia = nen[-1][4]
        th = quet_mo_hinh(da_dong, dang_chay, gia)
        if not th:
            continue
        so = 3 if TIEN[j] == "JPY" else 5
        rui_ro = abs(gia - th["cat_lo"])
        chenh = suc_manh[i] - suc_manh[j] if th["huong"] == 1 else suc_manh[j] - suc_manh[i]
        dong = {
            "cap": f"{TIEN[i]}/{TIEN[j]}", "goc": TIEN[i], "dinh": TIEN[j],
            "huong": "MUA" if th["huong"] == 1 else "BÁN",
            "mo_hinh": th["mo_hinh"], "gio_nen": th["gio_nen"],
            "chenh": round(chenh, 2),
            "gia": round(gia, so), "cat_lo": round(th["cat_lo"], so), "muc_tieu": round(th["muc_tieu"], so),
            "loi_lo": round(abs(th["muc_tieu"] - gia) / rui_ro, 1) if rui_ro > 0 else 0,
        }
        # Giá chờ: mức giá hồi về để lệnh đạt lời/lỗ 1:1,5 (cắt lỗ và mục tiêu giữ nguyên)
        if dong["loi_lo"] < 1.5:
            gia_cho = (th["muc_tieu"] + 1.5 * th["cat_lo"]) / 2.5
            if (th["huong"] == 1 and th["cat_lo"] < gia_cho < gia) or (th["huong"] == -1 and gia < gia_cho < th["cat_lo"]):
                dong["gia_cho"] = round(gia_cho, so)
        if chenh >= CHENH_LECH_TOI_THIEU:
            dat.append(dong)
        else:
            dong["ly_do"] = ("Sức mạnh ngày ngược chiều mô hình" if chenh < 0
                             else "Chênh lệch sức mạnh quá nhỏ")
            loai.append(dong)
    dat.sort(key=lambda d: -d["chenh"])
    loai.sort(key=lambda d: d["chenh"])

    canh_bao = []
    for c in TIEN:
        mua = sum(1 for d in dat if (d["huong"] == "MUA" and d["goc"] == c) or (d["huong"] == "BÁN" and d["dinh"] == c))
        ban = sum(1 for d in dat if (d["huong"] == "BÁN" and d["goc"] == c) or (d["huong"] == "MUA" and d["dinh"] == c))
        if mua >= 2:
            canh_bao.append(f"Đang mua {c} trong {mua} lệnh. Nếu {c} quay đầu, các lệnh này cùng lỗ. Nên chia nhỏ khối lượng.")
        if ban >= 2:
            canh_bao.append(f"Đang bán {c} trong {ban} lệnh. Nếu {c} bật tăng, các lệnh này cùng lỗ. Nên chia nhỏ khối lượng.")

    xep_hang = sorted(range(8), key=lambda c: -suc_manh[c])
    return {
        "cap_nhat": datetime.fromtimestamp(bay_gio, GIO_VN).strftime("%H:%M %d/%m/%Y"),
        "nen_4_gio_dong": gio_vn(nen_dong_moi_nhat) if nen_dong_moi_nhat else "",
        "ma_nen": nen_dong_moi_nhat,
        "so_cap_doc_duoc": len(tho),
        "suc_manh": [{"tien": TIEN[c], "phan_tram": round(suc_manh[c], 2)} for c in xep_hang],
        "dat": dat, "loai": loai, "canh_bao": canh_bao,
        "cai_dat": {"so_nen_dinh_day": SO_NEN_XET_DINH_DAY, "so_nen_gan_nhat": SO_NEN_GAN_NHAT_XET,
                    "chenh_toi_thieu": CHENH_LECH_TOI_THIEU, "so_nen_muc_tieu": SO_NEN_TIM_MUC_TIEU},
    }


def soan_tin(kq):
    sm = " | ".join(f"{x['tien']} {x['phan_tram']:+.2f}" for x in kq["suc_manh"])
    t = [f"<b>NẾN 4 GIỜ + SỨC MẠNH NGÀY</b>",
         f"Nến 4 giờ vừa đóng: {kq['nen_4_gio_dong']} (giờ Việt Nam)", "",
         "<b>Sức mạnh hôm nay</b> (mạnh → yếu)", sm, ""]
    if not kq["dat"]:
        t.append("Không có cặp nào đạt cả hai điều kiện.")
    else:
        t.append("<b>LỆNH ĐỀ XUẤT</b>")
        for k, d in enumerate(kq["dat"], 1):
            t.append(f"{k}. <b>{d['huong']} {d['cap']}</b>: {d['mo_hinh']} (nến {d['gio_nen']})")
            t.append(f"   Chênh sức mạnh {d['chenh']:.2f} | Giá {d['gia']}")
            t.append(f"   Cắt lỗ {d['cat_lo']} | Mục tiêu {d['muc_tieu']} | Lời/lỗ 1:{d['loi_lo']}")
            if d.get("gia_cho"):
                t.append(f"   Nên chờ giá hồi về {d['gia_cho']} (lời/lỗ 1:1,5)")
    if kq["canh_bao"]:
        t += ["", "<b>Lưu ý</b>"] + [f"• {c}" for c in kq["canh_bao"]]
    if DIA_CHI_WEB:
        t += ["", f"Xem chi tiết: {DIA_CHI_WEB}"]
    tin = "\n".join(t)
    return tin[:3900]


def gui_telegram(noi_dung):
    if not MA_BOT or not MA_CHAT:
        print("Chưa có mã bot hoặc mã chat Telegram, bỏ qua gửi tin.")
        return
    du_lieu = urllib.parse.urlencode({"chat_id": MA_CHAT, "text": noi_dung, "parse_mode": "HTML",
                                      "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{MA_BOT}/sendMessage", data=du_lieu)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print("Đã gửi Telegram:", r.status)
    except Exception as loi:
        print("Gửi Telegram lỗi:", loi)


def main():
    cu = {}
    if os.path.exists(FILE_DATA):
        try:
            with open(FILE_DATA, encoding="utf-8") as f:
                cu = json.load(f)
        except Exception:
            cu = {}
    kq = phan_tich()
    if kq["so_cap_doc_duoc"] < 20:
        print("Đọc được quá ít cặp, giữ nguyên dữ liệu cũ.")
        return
    with open(FILE_DATA, "w", encoding="utf-8") as f:
        json.dump(kq, f, ensure_ascii=False, indent=1)
    co_nen_moi = kq["ma_nen"] != cu.get("ma_nen")
    print(f"Nến 4 giờ đóng: {kq['nen_4_gio_dong']} | nến mới: {co_nen_moi} | lệnh đạt: {len(kq['dat'])}")
    if co_nen_moi or LUON_GUI:
        gui_telegram(soan_tin(kq))


if __name__ == "__main__":
    main()
