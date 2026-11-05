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
import subprocess
import sys
import tempfile
import time
import uuid
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# ---------------- Cài đặt (sửa ở đây nếu muốn) ----------------
SO_NEN_XET_DINH_DAY = 12    # Mô hình phải nằm ở đỉnh/đáy của bao nhiêu nến 4 giờ gần nhất
SO_NEN_GAN_NHAT_XET = 3     # Xét mô hình trong bao nhiêu nến 4 giờ vừa đóng
CHENH_LECH_TOI_THIEU = 0.15  # Chênh lệch sức mạnh tối thiểu giữa 2 đồng (đơn vị %)
SO_NEN_TIM_MUC_TIEU = 20    # Mục tiêu = đỉnh/đáy của bao nhiêu nến 4 giờ gần nhất
SO_GIO_DAU_NGAY = 2         # Trong bao nhiêu giờ đầu ngày giao dịch thì dùng sức mạnh của cả ngày hôm trước
SO_NEN_TREN_BIEU_DO = 45    # Số nến 4 giờ vẽ trên ảnh biểu đồ gửi Telegram và trên trang web
# ---------------------------------------------------------------

TIEN = ["EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY"]
CAP = [(i, j) for i in range(8) for j in range(i + 1, 8)]   # 28 cặp, tên chuẩn như EURUSD, GBPJPY...
NEW_YORK = ZoneInfo("America/New_York")
GIO_VN = timezone(timedelta(hours=7))
THU_MUC = os.path.dirname(os.path.abspath(__file__))
FILE_DATA = os.path.join(THU_MUC, "data.json")

MA_BOT = os.environ.get("TELEGRAM_TOKEN", "").strip()
# Có thể ghi nhiều mã, cách nhau bằng dấu phẩy: mã của anh, mã nhóm, mã kênh
DANH_SACH_CHAT = [m.strip() for m in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if m.strip()]
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
            gio_mo = khoa * 14400 - lech_gio_san(t)
            nhom[khoa] = {"t": t, "o": o, "h": h, "l": l, "c": c, "khoa": khoa, "dong": gio_mo + 14400}
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
    """Trả về danh sách (tên mô hình, số nến tạo mô hình)."""
    k, p = n[i], n[i - 1]
    ds = []
    # Nhấn chìm tăng: nến trước giảm, nến sau tăng đóng cửa vượt giá mở nến trước, thân lớn hơn
    if giam(p) and tang(k) and k["c"] >= p["o"] and than(k) > than(p):
        ds.append(("nhấn chìm tăng", 2))
    # Búa: râu dưới dài gấp đôi thân, râu trên ngắn, nến không quá nhỏ
    if rau_duoi(k) >= 2 * than(k) and rau_tren(k) <= 0.35 * bien(k) and bien(k) >= 0.6 * a:
        ds.append(("búa", 1))
    # Sao mai: nến giảm lớn, 1 hoặc 2 nến lưỡng lự, rồi nến tăng đóng trên giữa thân nến giảm lớn
    for so_giua in (1, 2):
        if i - 1 - so_giua < 0:
            continue
        lon = n[i - 1 - so_giua]
        giua = n[i - so_giua:i]
        if (giam(lon) and than(lon) > 0.5 * a and all(than(g) <= 0.6 * than(lon) for g in giua)
                and tang(k) and than(k) > 0.3 * a and k["c"] > (lon["o"] + lon["c"]) / 2):
            ds.append(("sao mai", so_giua + 2))
            break
    # Đáy nhíp: hai đáy bằng nhau, nến sau tăng
    if giam(p) and tang(k) and abs(k["l"] - p["l"]) < 0.1 * a and than(k) > 0.3 * a:
        ds.append(("đáy nhíp", 2))
    # Xuyên đâm: nến giảm lớn, nến tăng đóng trên giữa thân nhưng chưa vượt giá mở nến giảm
    if (giam(p) and than(p) > 0.5 * a and tang(k)
            and (p["o"] + p["c"]) / 2 < k["c"] < p["o"]):
        ds.append(("xuyên đâm", 2))
    # Quét đáy: râu chọc thủng đáy thấp nhất 12 nến trước rồi đóng cửa quay lên trên đáy đó
    day_cu = min(b["l"] for b in n[i - 12:i])
    if k["l"] < day_cu < k["c"] and k["c"] - k["l"] >= 0.5 * bien(k) and bien(k) >= 0.6 * a:
        ds.append(("quét đáy", 1))
    # Phá giả nến mẹ: 1-2 nến nằm gọn trong nến mẹ, nến sau chọc thủng đáy nến mẹ rồi đóng cửa quay vào trong
    for so_con in (1, 2):
        me = n[i - so_con - 1]
        con = n[i - so_con:i]
        if (bien(me) >= 0.8 * a and all(b["h"] <= me["h"] and b["l"] >= me["l"] for b in con)
                and k["l"] < me["l"] < k["c"] < me["h"]):
            ds.append(("phá giả nến mẹ", so_con + 2))
            break
    # Ba nến trong tăng: nến giảm lớn, nến nhỏ nằm trong thân nó, nến tăng đóng vượt giá mở nến giảm lớn
    pp = n[i - 2]
    if (giam(pp) and than(pp) > 0.5 * a and max(p["o"], p["c"]) <= pp["o"] and min(p["o"], p["c"]) >= pp["c"]
            and tang(k) and k["c"] > pp["o"]):
        ds.append(("ba nến trong tăng", 3))
    # Ba lính trắng: ba nến tăng thân dài liên tiếp, mỗi nến mở trong thân nến trước, đóng cao hơn, gần đỉnh nến
    ba = n[i - 2:i + 1]
    if (all(tang(b) and than(b) > 0.5 * a and rau_tren(b) <= 0.3 * bien(b) for b in ba)
            and all(ba[x - 1]["o"] <= ba[x]["o"] <= ba[x - 1]["c"] and ba[x]["c"] > ba[x - 1]["c"] for x in (1, 2))):
        ds.append(("ba lính trắng", 3))
    return ds


def mo_hinh_giam(n, i, a):
    """Trả về danh sách (tên mô hình, số nến tạo mô hình)."""
    k, p = n[i], n[i - 1]
    ds = []
    if tang(p) and giam(k) and k["c"] <= p["o"] and than(k) > than(p):
        ds.append(("nhấn chìm giảm", 2))
    if rau_tren(k) >= 2 * than(k) and rau_duoi(k) <= 0.35 * bien(k) and bien(k) >= 0.6 * a:
        ds.append(("sao băng", 1))
    for so_giua in (1, 2):
        if i - 1 - so_giua < 0:
            continue
        lon = n[i - 1 - so_giua]
        giua = n[i - so_giua:i]
        if (tang(lon) and than(lon) > 0.5 * a and all(than(g) <= 0.6 * than(lon) for g in giua)
                and giam(k) and than(k) > 0.3 * a and k["c"] < (lon["o"] + lon["c"]) / 2):
            ds.append(("sao hôm", so_giua + 2))
            break
    if tang(p) and giam(k) and abs(k["h"] - p["h"]) < 0.1 * a and than(k) > 0.3 * a:
        ds.append(("đỉnh nhíp", 2))
    if (tang(p) and than(p) > 0.5 * a and giam(k)
            and p["o"] < k["c"] < (p["o"] + p["c"]) / 2):
        ds.append(("mây đen", 2))
    # Quét đỉnh: râu chọc thủng đỉnh cao nhất 12 nến trước rồi đóng cửa quay xuống dưới đỉnh đó
    dinh_cu = max(b["h"] for b in n[i - 12:i])
    if k["c"] < dinh_cu < k["h"] and k["h"] - k["c"] >= 0.5 * bien(k) and bien(k) >= 0.6 * a:
        ds.append(("quét đỉnh", 1))
    # Phá giả nến mẹ: nến sau chọc thủng đỉnh nến mẹ rồi đóng cửa quay vào trong
    for so_con in (1, 2):
        me = n[i - so_con - 1]
        con = n[i - so_con:i]
        if (bien(me) >= 0.8 * a and all(b["h"] <= me["h"] and b["l"] >= me["l"] for b in con)
                and me["l"] < k["c"] < me["h"] < k["h"]):
            ds.append(("phá giả nến mẹ", so_con + 2))
            break
    # Ba nến trong giảm
    pp = n[i - 2]
    if (tang(pp) and than(pp) > 0.5 * a and max(p["o"], p["c"]) <= pp["c"] and min(p["o"], p["c"]) >= pp["o"]
            and giam(k) and k["c"] < pp["o"]):
        ds.append(("ba nến trong giảm", 3))
    # Ba quạ đen: ba nến giảm thân dài liên tiếp, mỗi nến mở trong thân nến trước, đóng thấp hơn, gần đáy nến
    ba = n[i - 2:i + 1]
    if (all(giam(b) and than(b) > 0.5 * a and rau_duoi(b) <= 0.3 * bien(b) for b in ba)
            and all(ba[x - 1]["c"] <= ba[x]["o"] <= ba[x - 1]["o"] and ba[x]["c"] < ba[x - 1]["c"] for x in (1, 2))):
        ds.append(("ba quạ đen", 3))
    return ds


def gio_vn(ts):
    return datetime.fromtimestamp(ts, GIO_VN).strftime("%H:%M %d/%m")


def quet_mo_hinh(da_dong, dang_chay, gia):
    """Tìm mô hình gần nhất còn hiệu lực. Trả về dict hoặc None."""
    n = da_dong
    if len(n) < SO_NEN_XET_DINH_DAY + SO_NEN_GAN_NHAT_XET + SO_NEN_TIM_MUC_TIEU:
        return None
    atr = tinh_atr(n)
    cuoi = len(n) - 1
    for i in range(cuoi, cuoi - SO_NEN_GAN_NHAT_XET, -1):
        a = atr[i]
        if a <= 0:
            continue
        cua_so = n[i - SO_NEN_XET_DINH_DAY:i + 1]
        sau = n[i + 1:] + dang_chay

        # Mô hình tăng: vùng nến tạo mô hình (ít nhất 3 nến) phải chứa đáy thấp nhất của cửa sổ
        ten, day, so_nen = [], None, 1
        for (tm, so) in mo_hinh_tang(n, i, a):
            d = min(b["l"] for b in n[i - max(3, so) + 1:i + 1])
            if d <= min(b["l"] for b in cua_so):
                ten.append(tm)
                so_nen = max(so_nen, so)
                day = d if day is None else min(day, d)
        if ten and gia > day and all(b["l"] > day for b in sau):
            cat_lo = day - 0.1 * a
            muc_tieu = max(b["h"] for b in n[-SO_NEN_TIM_MUC_TIEU:])
            if muc_tieu <= gia:
                muc_tieu = gia + 2 * (gia - cat_lo)
            return {"huong": 1, "mo_hinh": " + ".join(ten), "gio_nen": gio_vn(n[i]["dong"]), "chi_so": i, "so_nen": so_nen,
                    "cat_lo": cat_lo, "muc_tieu": muc_tieu}

        ten, dinh, so_nen = [], None, 1
        for (tm, so) in mo_hinh_giam(n, i, a):
            d = max(b["h"] for b in n[i - max(3, so) + 1:i + 1])
            if d >= max(b["h"] for b in cua_so):
                ten.append(tm)
                so_nen = max(so_nen, so)
                dinh = d if dinh is None else max(dinh, d)
        if ten and gia < dinh and all(b["h"] < dinh for b in sau):
            cat_lo = dinh + 0.1 * a
            muc_tieu = min(b["l"] for b in n[-SO_NEN_TIM_MUC_TIEU:])
            if muc_tieu >= gia:
                muc_tieu = gia - 2 * (cat_lo - gia)
            return {"huong": -1, "mo_hinh": " + ".join(ten), "gio_nen": gio_vn(n[i]["dong"]), "chi_so": i, "so_nen": so_nen,
                    "cat_lo": cat_lo, "muc_tieu": muc_tieu}
    return None


def dau_ngay_san(ts):
    """Thời điểm mở cửa ngày giao dịch của sàn chứa thời điểm ts (0 giờ sàn = 17 giờ New York)."""
    lech = lech_gio_san(ts)
    return (ts + lech) // 86400 * 86400 - lech


def cach_do_suc_manh(bay_gio, nen_mau):
    """Sức mạnh tính giống MarketMilk: % thay đổi từ giá mở cửa ngày của sàn.
    Ngay đầu ngày (sức mạnh chưa hình thành) thì dùng sức mạnh cả ngày vừa kết thúc."""
    dau = dau_ngay_san(bay_gio)
    if bay_gio - dau >= SO_GIO_DAU_NGAY * 3600:
        return "từ giá mở cửa ngày", dau, bay_gio
    truoc = [x[0] for x in nen_mau if x[0] < dau]
    if not truoc:
        return "từ giá mở cửa ngày", dau, bay_gio
    return "cả ngày hôm trước", dau_ngay_san(truoc[-1]), dau


def thay_doi_phan_tram(nen_gio, moc_dau, moc_cuoi):
    """% thay đổi từ giá mở của nến giờ đầu tiên sau mốc đầu, tới giá đóng của nến giờ cuối cùng trước mốc cuối."""
    gia_dau = next((o for (t, o, h, l, c) in nen_gio if t >= moc_dau), None)
    gia_cuoi = None
    for (t, o, h, l, c) in nen_gio:
        if t < moc_cuoi:
            gia_cuoi = c
    if not gia_dau or gia_cuoi is None:
        return 0.0
    return (gia_cuoi - gia_dau) / gia_dau * 100


def phan_tich(lay_nen=lay_nen_gio, bay_gio=None):
    bay_gio = bay_gio or int(time.time())
    tong = [0.0] * 8
    dem = [0] * 8
    tho = {}
    for (i, j) in CAP:
        ten = TIEN[i] + TIEN[j]
        nen = [x for x in lay_nen(ten) if x[0] < bay_gio]
        if len(nen) < 100:
            print(f"Thiếu dữ liệu {ten}, bỏ qua")
            continue
        tho[(i, j)] = nen
        if len(tho) == 1:
            cach_do, moc_dau, moc_cuoi = cach_do_suc_manh(bay_gio, nen)
        pct = thay_doi_phan_tram(nen, moc_dau, moc_cuoi)
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
            nen_dong_moi_nhat = max(nen_dong_moi_nhat, da_dong[-1]["dong"])
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
        # Nến 4 giờ gần nhất để vẽ biểu đồ (gồm cả nến đang chạy)
        tat_ca = da_dong + dang_chay
        bat_dau = max(0, len(tat_ca) - SO_NEN_TREN_BIEU_DO)
        dong["nen"] = [[b["dong"], round(b["o"], so), round(b["h"], so), round(b["l"], so), round(b["c"], so)]
                       for b in tat_ca[bat_dau:]]
        dong["chi_so_mh"] = th["chi_so"] - bat_dau
        dong["so_le"] = so
        dong["so_nen_mh"] = th["so_nen"]
        if chenh >= CHENH_LECH_TOI_THIEU:
            dat.append(dong)
        else:
            dong["ly_do"] = ("Sức mạnh ngày ngược chiều mô hình" if chenh < 0
                             else "Chênh lệch sức mạnh quá nhỏ")
            for khoa in ("nen", "chi_so_mh", "so_nen_mh"):
                dong.pop(khoa, None)
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
        "cach_do": cach_do,
        "suc_manh": [{"tien": TIEN[c], "phan_tram": round(suc_manh[c], 2)} for c in xep_hang],
        "dat": dat, "loai": loai, "canh_bao": canh_bao,
        "cai_dat": {"so_nen_dinh_day": SO_NEN_XET_DINH_DAY, "so_nen_gan_nhat": SO_NEN_GAN_NHAT_XET,
                    "chenh_toi_thieu": CHENH_LECH_TOI_THIEU, "so_nen_muc_tieu": SO_NEN_TIM_MUC_TIEU},
    }


def so(gia, so_le):
    return f"{gia:.{so_le}f}"


def soan_tin_tom_tat(kq):
    """Tin nhắn đầu tiên: sức mạnh và danh sách lệnh, dòng ngắn cho dễ đọc trên điện thoại."""
    lon_nhat = max(abs(x["phan_tram"]) for x in kq["suc_manh"]) or 1
    dong_sm = []
    for x in kq["suc_manh"]:
        dai = round(abs(x["phan_tram"]) / lon_nhat * 8)
        thanh = ("█" if x["phan_tram"] >= 0 else "░") * max(dai, 1)
        dong_sm.append(f"{x['tien']} {x['phan_tram']:+.2f}  {thanh}")
    t = ["📊 <b>BÁO CÁO NẾN 4 GIỜ</b>",
         f"Nến đóng lúc <b>{kq['nen_4_gio_dong']}</b>", "",
         f"<b>Sức mạnh tiền tệ</b> ({kq['cach_do']})",
         "<pre>" + "\n".join(dong_sm) + "</pre>"]
    if not kq["dat"]:
        t += ["Không có cặp nào đạt đủ hai điều kiện:", "mô hình nến đảo chiều + sức mạnh thuận chiều."]
    else:
        t.append(f"<b>{len(kq['dat'])} lệnh đề xuất</b> (ảnh chi tiết ở tin sau)")
        for k, d in enumerate(kq["dat"], 1):
            dau = "🟢" if d["huong"] == "MUA" else "🔴"
            t.append(f"{dau} <b>{d['huong']} {d['cap']}</b> · {d['mo_hinh']}")
    if kq["canh_bao"]:
        t += ["", "⚠️ <b>Lưu ý</b>"]
        for c in kq["canh_bao"]:
            t.append("• " + c.split(". Nếu")[0] + " → nên chia nhỏ khối lượng")
    if DIA_CHI_WEB:
        t += ["", f'<a href="{DIA_CHI_WEB}">Mở trang Bàn Ghép Cặp H4</a>']
    return "\n".join(t)[:4000]


def soan_chu_thich_anh(k, d):
    """Chú thích đi kèm ảnh biểu đồ của từng lệnh."""
    sl = d["so_le"]
    vao = d.get("gia_cho") or d["gia"]
    loi_lo = abs(d["muc_tieu"] - vao) / abs(vao - d["cat_lo"]) if vao != d["cat_lo"] else 0
    dau = "🟢" if d["huong"] == "MUA" else "🔴"
    cach_vao = "Lệnh chờ" if d.get("gia_cho") else "Vào ngay"
    bang = ([f"Giá hiện tại {so(d['gia'], sl):>10}"] if d.get("gia_cho") else []) + [
            f"{cach_vao:<12} {so(vao, sl):>10}",
            f"Cắt lỗ       {so(d['cat_lo'], sl):>10}",
            f"Mục tiêu     {so(d['muc_tieu'], sl):>10}",
            f"Lời/lỗ       {('1 : ' + format(loi_lo, '.1f')):>10}"]
    t = [f"{dau} <b>{k}. {d['huong']} {d['cap']}</b>",
         f"{d['mo_hinh'].capitalize()} · nến đóng {d['gio_nen']}",
         "<pre>" + "\n".join(bang) + "</pre>",
         f"Chênh sức mạnh {d['goc']}–{d['dinh']}: {abs(d['chenh']):.2f}"]
    if d.get("gia_cho"):
        t.append(f"Giá đang xa mô hình, chờ hồi về {so(vao, sl)} để đạt lời/lỗ 1 : 1,5.")
    return "\n".join(t)[:1000]


def chuan_bi_matplotlib():
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "matplotlib"])
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def ve_bieu_do(d, duong_dan):
    """Vẽ nến 4 giờ kèm vùng vào lệnh, cắt lỗ, mục tiêu. Lưu ảnh PNG."""
    plt = chuan_bi_matplotlib()
    from matplotlib.patches import Rectangle
    nen = d["nen"]
    sl = d["so_le"]
    vao = d.get("gia_cho") or d["gia"]
    mua = d["huong"] == "MUA"
    XANH, DO, LAM, VANG, XAM, CHU = "#16a06a", "#d84a3c", "#2563c9", "#e8a317", "#8a96a3", "#1c2733"

    fig, ax = plt.subplots(figsize=(8, 5.4), dpi=140)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#fbfcfd")
    n = len(nen)
    for k, (_, o, h, l, c) in enumerate(nen):
        mau = XANH if c >= o else DO
        ax.plot([k, k], [l, h], color=mau, linewidth=1, zorder=2)
        ax.add_patch(Rectangle((k - 0.32, min(o, c)), 0.64, max(abs(c - o), 1e-9),
                               facecolor=mau, edgecolor=mau, zorder=3))

    # Vùng lời và lỗ tính từ nến mô hình sang phải
    x0, x1 = d["chi_so_mh"] + 0.5, n + 3
    ax.add_patch(Rectangle((x0, min(vao, d["cat_lo"])), x1 - x0, abs(vao - d["cat_lo"]),
                           facecolor=DO, alpha=0.10, zorder=1))
    ax.add_patch(Rectangle((x0, min(vao, d["muc_tieu"])), x1 - x0, abs(vao - d["muc_tieu"]),
                           facecolor=XANH, alpha=0.10, zorder=1))
    # Đánh dấu nến mô hình
    i = d["chi_so_mh"]
    ax.axvspan(i - d.get("so_nen_mh", 1) + 0.5, i + 0.5, color=VANG, alpha=0.22, zorder=0)
    cum = nen[max(0, i - d.get("so_nen_mh", 1) + 1):i + 1]
    y_mui = min(x[3] for x in cum) if mua else max(x[2] for x in cum)
    lech = (max(x[2] for x in nen) - min(x[3] for x in nen)) * 0.07
    ax.annotate(d["mo_hinh"], xy=(i - (d.get("so_nen_mh", 1) - 1) / 2, y_mui), xytext=(i - (d.get("so_nen_mh", 1) - 1) / 2, y_mui - lech if mua else y_mui + lech),
                ha="center", va="top" if mua else "bottom", fontsize=9, color=CHU, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=CHU, lw=1.2), zorder=5)

    # Các vạch giá
    duong = [(d["muc_tieu"], XANH, "Mục tiêu", "-"),
             (vao, LAM, "Lệnh chờ" if d.get("gia_cho") else "Vào lệnh", "-"),
             (d["cat_lo"], DO, "Cắt lỗ", "-")]
    if d.get("gia_cho"):
        duong.append((d["gia"], XAM, "Giá hiện tại", ":"))
    for y, mau, _, kieu in duong:
        ax.plot([x0 if mau != XAM else -0.5, x1], [y, y], color=mau, lw=1.6, ls=kieu, zorder=4)

    # Nhãn bên phải, tránh chồng lên nhau
    y_min = min(min(x[3] for x in nen), d["cat_lo"], d["muc_tieu"])
    y_max = max(max(x[2] for x in nen), d["cat_lo"], d["muc_tieu"])
    khoang = (y_max - y_min) * 0.065
    nhan = sorted(duong, key=lambda x: x[0])
    vi_tri = []
    for y, *_ in nhan:
        vi_tri.append(max(y, vi_tri[-1] + khoang) if vi_tri else y)
    for (y, mau, ten, _), yv in zip(nhan, vi_tri):
        ax.text(n + 3.3, yv, f"{ten}\n{so(y, sl)}", color="white", fontsize=8.5, va="center", ha="left",
                fontweight="bold", bbox=dict(boxstyle="round,pad=0.3", fc=mau, ec="none"), clip_on=False, zorder=6)

    ax.set_xlim(-1, n + 3)
    ax.set_ylim(y_min - khoang * 1.2, max(y_max, vi_tri[-1]) + khoang * 1.2)
    buoc = max(1, n // 6)
    ax.set_xticks(range(0, n, buoc))
    ax.set_xticklabels([datetime.fromtimestamp(nen[k][0], GIO_VN).strftime("%d/%m\n%H:%M") for k in range(0, n, buoc)],
                       fontsize=8, color=XAM)
    ax.yaxis.tick_left()
    ax.tick_params(axis="y", labelsize=8, colors=XAM)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: so(v, sl)))
    ax.grid(axis="y", color="#e6eaee", lw=0.8)
    for canh in ("top", "right"):
        ax.spines[canh].set_visible(False)
    for canh in ("left", "bottom"):
        ax.spines[canh].set_color("#d5dbe1")
    ax.set_title(f"{d['huong']} {d['cap']}  ·  khung 4 giờ  ·  {d['mo_hinh']}", loc="left",
                 fontsize=12, fontweight="bold", color=XANH if mua else DO)
    fig.subplots_adjust(left=0.1, right=0.83, top=0.92, bottom=0.12)
    fig.savefig(duong_dan)
    plt.close(fig)


def goi_telegram(phuong_thuc, du_lieu, tep=None):
    url = f"https://api.telegram.org/bot{MA_BOT}/{phuong_thuc}"
    if tep is None:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(du_lieu).encode())
    else:
        ranh_gioi = uuid.uuid4().hex
        than = b""
        for k, v in du_lieu.items():
            than += (f"--{ranh_gioi}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
        with open(tep, "rb") as f:
            anh = f.read()
        than += (f"--{ranh_gioi}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"bieu_do.png\"\r\n"
                 "Content-Type: image/png\r\n\r\n").encode() + anh + f"\r\n--{ranh_gioi}--\r\n".encode()
        req = urllib.request.Request(url, data=than,
                                     headers={"Content-Type": f"multipart/form-data; boundary={ranh_gioi}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"Telegram {phuong_thuc}:", r.status)
    except Exception as loi:
        print(f"Telegram {phuong_thuc} lỗi:", loi)


def gui_bao_cao(kq):
    if not MA_BOT or not DANH_SACH_CHAT:
        print("Chưa có mã bot hoặc mã chat Telegram, bỏ qua gửi tin.")
        return
    # Vẽ ảnh một lần, gửi cho tất cả nơi nhận
    thu_muc = tempfile.mkdtemp()
    anh = []
    for k, d in enumerate(kq["dat"][:8], 1):
        duong_dan = os.path.join(thu_muc, f"{k}.png")
        try:
            ve_bieu_do(d, duong_dan)
        except Exception as loi:
            print(f"Vẽ ảnh {d['cap']} lỗi:", loi)
            duong_dan = None
        anh.append((soan_chu_thich_anh(k, d), duong_dan))
    tom_tat = soan_tin_tom_tat(kq)
    for ma in DANH_SACH_CHAT:
        goi_telegram("sendMessage", {"chat_id": ma, "text": tom_tat, "parse_mode": "HTML",
                                     "disable_web_page_preview": "true"})
        for chu_thich, duong_dan in anh:
            if duong_dan:
                goi_telegram("sendPhoto", {"chat_id": ma, "caption": chu_thich, "parse_mode": "HTML"}, tep=duong_dan)
            else:
                goi_telegram("sendMessage", {"chat_id": ma, "text": chu_thich, "parse_mode": "HTML"})


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
        gui_bao_cao(kq)


if __name__ == "__main__":
    main()
