# Copyright (C) 2026 Nguyen The Viet, Vu Thi Mai Anh, Do Huu An Phu, Phan Thuy Tram
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Data loader and preprocessing module using Pandas for Shopee datasets."""

import io
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from ._helpers import to_float, to_int

REQUIRED_COLUMNS = [
    "shop_id",
    "item_id",
    "product_name",
    "price",
    "price_original",
    "discount_percent",
    "monthly_sold_value",
    "rating_count",
    "rating",
    "ctime",
    "voucher_discount",
    "voucher_min_spend",
    "voucher_start_time",
    "voucher_end_time",
    "catid",
    "date",
]

PROMOTIONAL_CATEGORIES = [
    r"sản\s*phẩm\s*mới",
    r"san\s*pham\s*moi",
    r"tất\s*cả\s*sản\s*phẩm",
    r"tat\s*ca\s*san\s*pham",
    r"top\s*bán\s*chạy",
    r"sản\s*phẩm\s*bán\s*chạy",
    r"bán\s*chạy",
    r"best\s*seller",
    r"siêu\s*sale",
    r"mua\s*1\s*tặng\s*1",
    r"ưu\s*đãi",
    r"deal",
    r"giảm\s*giá",
    r"thùng\s*bánh",
    r"bánh\s*kẹo\s*sỉ",
    r"sỉ",
    r"cuồng\s*nhiệt",
    r"độc\s*quyền\s*online",
    r"box\s*độc\s*quyền",
    r"combo\s*mix",
    r"combo\s*tết",
    r"kinh\s*đô\s*tết",
]

_PROMO_REGEX = re.compile(r"|".join(PROMOTIONAL_CATEGORIES), re.IGNORECASE)

_GIFT_REGEX = re.compile(
    r"(\bquà\s*tặng\s*không\s*bán\b|\bhàng\s*tặng\s*không\s*bán\b|\bhàng\s*tặng\b|\[\s*quà\s*tặng|\[\s*gift\s*\]|\bquà\s*tặng\s*\||\bquà\s*tặng\s*-)",
    re.IGNORECASE,
)


def is_promotional_category(cat_name: Optional[str]) -> bool:
    """Kiểm tra xem danh mục có phải là danh mục quảng bá / khuyến mãi chung hay không."""
    if not cat_name or str(cat_name).strip() in ("", "None", "nan", "Khác", "Other"):
        return True
    return bool(_PROMO_REGEX.search(str(cat_name)))


def is_gift_product(product_name: Optional[str]) -> bool:
    """Kiểm tra xem tên sản phẩm có phải là hàng quà tặng kèm không."""
    if not product_name:
        return False
    name = str(product_name).strip()
    if _GIFT_REGEX.search(name):
        return True
    lower = name.lower()
    if lower.startswith("quà tặng") or lower.startswith("[quà tặng") or lower.startswith("(quà tặng") or lower.startswith("[gift"):
        return True
    if "quà tặng không bán" in lower or "quà tặng kèm" in lower or "hàng tặng" in lower:
        return True
    return False


def _match_keywords_line(product_name: str) -> str:
    """Fallback gán dòng sản phẩm theo từ khóa thương hiệu / nhóm ngành đặc trưng."""
    name = str(product_name or "").lower()

    # 1. Quasure / Không đường / Ăn kiêng tiểu đường
    if "quasure" in name or "sugar free" in name or "không đường" in name:
        return "Quasure Sugar Free"
    # 2. Gooka / Nougat
    if "gooka" in name or "nougat" in name:
        return "Gooka Nougat Filling"
    # 3. Kẹo Trẻ Em / Zoo / Thạch
    if any(w in name for w in ["zoo", "cho bé", "trẻ em", "kem tuyết", "sâu kỳ thú", "sâu tuyết"]):
        return "Kẹo Cho Bé"
    # 4. Bánh ăn sáng / Bánh mì / Sandwich / Olive
    if any(w in name for w in ["ăn sáng", "sandwich", "bông lan olive", "bánh tươi olive", "bánh mì", "castella"]):
        return "Bánh Ăn Sáng"
    # 5. Bánh dinh dưỡng / Ngũ cốc / Ăn kiêng
    if any(w in name for w in ["dinh dưỡng", "ăn kiêng", "tiểu đường", "ngũ cốc"]):
        return "Bánh Dinh Dưỡng"
    # 6. Kẹo ăn vặt / Kẹo các loại
    if any(w in name for w in ["sumika", "cheery", "welly", "migita", "tứ quý", "michoco", "kẹo dẻo", "kẹo mút", "kẹo cứng", "kẹo ngậm", "kẹo mềm", "kẹo thạch", "kẹo", "gum"]):
        return "Kẹo Ăn Vặt"
    # 7. Bánh ăn vặt / Bánh các loại
    if any(w in name for w in ["hura", "goody", "jamy", "cookies", "bánh quy", "bánh cracker", "bánh bông lan", "bánh"]):
        return "Bánh Ăn Vặt"

    return "Khác"


_LINE_PATTERNS = [
    (re.compile(r"\b(zoo|em\s*b[eé]|kid|tr[eẻ]\s*em)\b", re.IGNORECASE), "Kẹo Cho Bé"),
    (re.compile(r"\b(quasure|sugar\s*free|ti[eể]u\s*[dđ][uư][oờ]ng)\b", re.IGNORECASE), "Quasure Sugar Free"),
    (re.compile(r"\b(gooka|nougat)\b", re.IGNORECASE), "Gooka Nougat Filling"),
    (re.compile(r"\b(sumika|cheery|welly|migita|tứ\s*quý|k[eẹ]o)\b", re.IGNORECASE), "Kẹo Ăn Vặt"),
    (re.compile(r"\b(hura|goody|jamy|b[aá]nh)\b", re.IGNORECASE), "Bánh Ăn Vặt"),
]


class LoaderError(Exception):
    """Exception raised for errors during dataset loading and validation."""

    def __init__(self, message: str, missing_columns: Optional[List[str]] = None):
        super().__init__(message)
        self.missing_columns = missing_columns or []


def load_category_mapping(shop_id: Optional[str] = None, base_dir: Optional[Union[str, Path]] = None) -> Dict[str, str]:
    """Đọc category_list.csv và product_categories.csv để tạo ánh xạ item_id -> display_name.
    Ưu tiên bỏ qua các danh mục khuyến mãi/quảng bá chung nếu có danh mục cụ thể hơn."""
    import os
    candidate_roots = []
    if base_dir:
        candidate_roots.append(Path(base_dir))
    mod_dir = Path(__file__).resolve().parent
    candidate_roots.extend([
        mod_dir.parent.parent / "mockups" / "Data" / "country_code=vn",
        mod_dir.parent.parent / "Data" / "country_code=vn",
        mod_dir.parent.parent / "data",
    ])

    root_found = None
    for r in candidate_roots:
        if (r / "dataset=category_list").is_dir() or (r / "dataset=product_categories").is_dir():
            root_found = r
            break

    if not root_found:
        return {}

    # Đọc category_list.csv
    cat_names: Dict[str, str] = {}
    cat_list_dir = root_found / "dataset=category_list"
    shop_subdirs = [f"shop_id={shop_id}"] if shop_id else ([p.name for p in cat_list_dir.iterdir() if p.is_dir()] if cat_list_dir.exists() else [])
    for sdir in shop_subdirs:
        p = cat_list_dir / sdir / "category_list.csv"
        if p.is_file():
            try:
                cat_df = pd.read_csv(p, dtype=str)
                for _, row in cat_df.iterrows():
                    cid = row.get("shop_category_id")
                    name = row.get("display_name")
                    if pd.notna(cid) and pd.notna(name):
                        cat_names[str(cid).strip()] = str(name).strip()
            except Exception:
                pass

    # Đọc product_categories.csv -> thu thập tất cả categories cho từng item_id
    item_all_cats: Dict[str, List[str]] = {}
    prod_cat_dir = root_found / "dataset=product_categories"
    p_shop_subdirs = [f"shop_id={shop_id}"] if shop_id else ([p.name for p in prod_cat_dir.iterdir() if p.is_dir()] if prod_cat_dir.exists() else [])
    for sdir in p_shop_subdirs:
        p = prod_cat_dir / sdir / "product_categories.csv"
        if p.is_file():
            try:
                pc_df = pd.read_csv(p, dtype=str)
                for _, row in pc_df.iterrows():
                    iid = row.get("item_id")
                    cid = row.get("category_id") or row.get("category_slug")
                    if pd.notna(iid) and pd.notna(cid):
                        iid_str = str(iid).strip()
                        cid_str = str(cid).strip()
                        cname = cat_names.get(cid_str, cid_str)
                        if cname:
                            item_all_cats.setdefault(iid_str, []).append(cname)
            except Exception:
                pass

    # Ưu tiên chọn danh mục cụ thể (không phải khuyến mãi / quảng bá chung)
    item_to_cat: Dict[str, str] = {}
    for iid_str, cats in item_all_cats.items():
        specific_cats = [c for c in cats if not is_promotional_category(c)]
        if specific_cats:
            item_to_cat[iid_str] = specific_cats[0]
        elif cats:
            item_to_cat[iid_str] = cats[0]

    return item_to_cat


def assign_product_line(
    product_name: str,
    catid: Any = None,
    total_distinct_catids: int = 1,
    item_id: Any = None,
    category_mapping: Optional[Dict[str, str]] = None,
    category_list: Optional[List[str]] = None,
) -> str:
    """Categorizes product into a product line:
    1. Nếu tên sản phẩm là quà tặng -> 'Quà Tặng'
    2. Nếu có trong product_categories (đã lọc bỏ promo) -> dùng danh mục đó
    3. Fallback khớp tên sản phẩm theo tên danh mục trong category_list & từ khóa đặc trưng
    Đảm bảo 100% SKU đều có dòng sản phẩm phù hợp.
    """
    name = str(product_name or "")

    # 1. Hàng quà tặng
    if is_gift_product(name):
        return "Quà Tặng"

    # 2. Khớp từ category_mapping nếu là danh mục cụ thể (không phải promo/Khác)
    if category_mapping and item_id is not None:
        iid_str = str(item_id).strip()
        if iid_str in category_mapping:
            cat = category_mapping[iid_str]
            if cat and not is_promotional_category(cat) and cat not in ("Khác", "Other"):
                return cat

    # 3. Fallback khớp tên sản phẩm với danh mục trong category_list (loại bỏ promo)
    name_lower = name.lower()
    if category_list:
        for cname in category_list:
            if is_promotional_category(cname):
                continue
            cname_clean = str(cname).strip()
            cname_lower = cname_clean.lower()
            if cname_lower in name_lower:
                return cname_clean
            tokens = [t for t in re.split(r"\s+", cname_lower) if len(t) > 3 and t not in ("bánh", "kẹo", "tổng", "hợp", "thực", "phẩm")]
            if tokens and all(t in name_lower for t in tokens):
                return cname_clean

    # 4. Fallback khớp theo từ khóa đặc trưng thương hiệu / ngành
    matched_line = _match_keywords_line(name)
    if matched_line and matched_line != "Khác":
        return matched_line

    if total_distinct_catids > 1 and catid not in (None, "", "None", "nan"):
        return f"Cat_{catid}"

    return "Bánh Ăn Vặt" if "bánh" in name_lower else ("Kẹo Ăn Vặt" if "kẹo" in name_lower else "Bánh Ăn Vặt")


def load_shop_category_list(shop_id: Optional[str] = None, base_dir: Optional[Union[str, Path]] = None) -> List[str]:
    """Đọc category_list.csv để lấy danh sách tên các danh mục (loại bỏ danh mục trùng lặp/rỗng)."""
    candidate_roots = []
    if base_dir:
        candidate_roots.append(Path(base_dir))
    mod_dir = Path(__file__).resolve().parent
    candidate_roots.extend([
        mod_dir.parent.parent / "mockups" / "Data" / "country_code=vn",
        mod_dir.parent.parent / "Data" / "country_code=vn",
        mod_dir.parent.parent / "data",
    ])

    root_found = None
    for r in candidate_roots:
        if (r / "dataset=category_list").is_dir():
            root_found = r
            break

    if not root_found:
        return []

    cat_list_dir = root_found / "dataset=category_list"
    shop_subdirs = [f"shop_id={shop_id}"] if shop_id else ([p.name for p in cat_list_dir.iterdir() if p.is_dir()] if cat_list_dir.exists() else [])
    display_names: List[str] = []
    seen = set()
    for sdir in shop_subdirs:
        p = cat_list_dir / sdir / "category_list.csv"
        if p.is_file():
            try:
                cat_df = pd.read_csv(p, dtype=str)
                for name in cat_df.get("display_name", []):
                    if pd.notna(name):
                        name_str = str(name).strip()
                        if name_str and name_str not in seen:
                            seen.add(name_str)
                            display_names.append(name_str)
            except Exception:
                pass
    return display_names


def load_products_dataframe(source: Union[str, Path, bytes, io.StringIO, io.BytesIO], category_mapping: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """Loads raw Shopee products data into a cleaned Pandas DataFrame."""
    try:
        if hasattr(source, "read_bytes"):
            df = pd.read_csv(io.BytesIO(source.read_bytes()), dtype=str)
        elif isinstance(source, (str, Path)) and (isinstance(source, Path) or Path(source).exists()):
            df = pd.read_csv(source, dtype=str)
        elif isinstance(source, bytes):
            df = pd.read_csv(io.BytesIO(source), dtype=str)
        elif isinstance(source, io.StringIO):
            df = pd.read_csv(source, dtype=str)
        elif isinstance(source, io.BytesIO):
            df = pd.read_csv(source, dtype=str)
        elif isinstance(source, str):
            df = pd.read_csv(io.StringIO(source), dtype=str)
        else:
            raise LoaderError("Unsupported source format.")
    except Exception as exc:
        raise LoaderError(f"Failed to parse CSV: {exc}") from exc

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise LoaderError(f"Missing required columns in CSV: {missing}", missing_columns=missing)

    # Clean and standardize types
    df = df.dropna(subset=["item_id"]).copy()
    df["item_id"] = df["item_id"].astype(str).str.strip()
    df["shop_id"] = df["shop_id"].astype(str).str.strip()
    df["product_name"] = df["product_name"].fillna("").astype(str)

    numeric_cols = [
        "price",
        "price_original",
        "discount_percent",
        "monthly_sold_value",
        "rating_count",
        "rating",
        "ctime",
        "voucher_discount",
        "voucher_min_spend",
        "voucher_start_time",
        "voucher_end_time",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # Line assignment
    category_list = None
    if not df.empty:
        first_shop_id = str(df["shop_id"].iloc[0]).strip() if pd.notna(df["shop_id"].iloc[0]) else None
        if category_mapping is None:
            category_mapping = load_category_mapping(first_shop_id)
        category_list = load_shop_category_list(first_shop_id)

    distinct_catids = df["catid"].dropna().replace("", None).nunique()
    df["line"] = df.apply(
        lambda r: assign_product_line(
            r["product_name"],
            r.get("catid"),
            distinct_catids,
            item_id=r.get("item_id"),
            category_mapping=category_mapping,
            category_list=category_list,
        ),
        axis=1,
    )

    return df


def load_csv_data(
    source: Union[str, Path, bytes, io.StringIO, io.BytesIO]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Parses CSV data into (data_pool, snapshots).
    - snapshots: list of all raw snapshot records across time
    - data_pool: deduplicated list of unique SKUs for the shop
    """
    df = load_products_dataframe(source)
    snapshots = df.to_dict(orient="records")

    # Dedup by item_id (keeping row with max monthly_sold_value)
    df_sorted = df.sort_values(by=["monthly_sold_value", "price"], ascending=[False, False])
    df_dedup = df_sorted.drop_duplicates(subset=["item_id"], keep="first")
    data_pool = df_dedup.to_dict(orient="records")

    return data_pool, snapshots


def build_observations_from_snapshots(snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Builds cross-time observation pairs for price elasticity estimation."""
    by_item: Dict[str, List[Dict[str, Any]]] = {}
    for r in snapshots:
        iid = str(r.get("item_id", ""))
        if not iid:
            continue
        by_item.setdefault(iid, []).append(r)

    observations: List[Dict[str, Any]] = []
    for iid, rows in by_item.items():
        if len(rows) < 2:
            continue
        # Sort chronologically by date if available
        rows_sorted = sorted(rows, key=lambda x: str(x.get("date", "")))
        for i in range(1, len(rows_sorted)):
            prev = rows_sorted[i - 1]
            curr = rows_sorted[i]

            p_prev = to_float(prev.get("price"))
            p_curr = to_float(curr.get("price"))
            s_prev = to_float(prev.get("monthly_sold_value"))
            s_curr = to_float(curr.get("monthly_sold_value"))

            if p_prev <= 0 or p_curr <= 0 or p_prev == p_curr:
                continue

            delta_log_p = math.log(p_curr) - math.log(p_prev)
            delta_log_s = math.log1p(s_curr) - math.log1p(s_prev)

            observations.append({
                "item_id": iid,
                "shop_id": str(curr.get("shop_id", "")),
                "line": str(curr.get("line", "Other")),
                "delta_log_p": delta_log_p,
                "delta_log_s": delta_log_s,
                "price": p_curr,
                "monthly_sold_value": s_curr,
            })

    return observations
