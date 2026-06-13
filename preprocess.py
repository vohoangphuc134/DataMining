import pandas as pd
import os

# =========================
# 1. Đọc dữ liệu từ thư mục output
# =========================

folder = "output"

csv_files = [
    os.path.join(folder, file)
    for file in os.listdir(folder)
    if file.endswith(".csv")
    and not file.startswith("cleaned_")
]

dataframes = []

for file in csv_files:
    df_temp = pd.read_csv(file)
    df_temp["source_file"] = os.path.basename(file)
    dataframes.append(df_temp)
    print(f"Đã đọc: {file} - {df_temp.shape}")

df = pd.concat(dataframes, ignore_index=True)

print("Tổng dữ liệu ban đầu:", df.shape)


# =========================
# 2. Chuẩn hóa tên cột
# =========================

df.columns = (
    df.columns
    .str.strip()
    .str.lower()
    .str.replace(" ", "_")
    .str.replace("-", "_")
)

print("Các cột hiện có:")
print(df.columns)


# =========================
# 3. Xóa dữ liệu trùng
# =========================

# Xóa dòng trùng hoàn toàn
df = df.drop_duplicates()

# Xóa bất động sản trùng giữa các nguồn
df = df.drop_duplicates(
    subset=[
        "property_type",
        "district",
        "price",
        "area"
    ]
)

# =========================
# 4. Chuyển đổi giá và diện tích
# =========================

# price trong dữ liệu của bạn đang là đơn vị TRIỆU đồng
df["price_clean"] = pd.to_numeric(df["price"], errors="coerce")
df["price_vnd"] = df["price_clean"] * 1_000_000

df["area_clean"] = pd.to_numeric(df["area"], errors="coerce")


# =========================
# 5. Xử lý dữ liệu thiếu bắt buộc
# =========================

df = df.dropna(subset=[
    "price_vnd",
    "area_clean",
    "district",
    "property_type"
])


# =========================
# 6. Lọc giá trị không hợp lệ
# =========================

df = df[df["price_vnd"] > 0]
df = df[df["area_clean"] > 0]

# Diện tích hợp lý
df = df[df["area_clean"] >= 5]
df = df[df["area_clean"] <= 1000]

# Giá hợp lý: từ 100 triệu đến 500 tỷ
df = df[df["price_vnd"] >= 100_000_000]
df = df[df["price_vnd"] <= 500_000_000_000]



# =========================
# 7. Tạo cột giá trên m2
# =========================

df["price_per_m2_clean"] = df["price_vnd"] / df["area_clean"]


# =========================
# 8. Xử lý dữ liệu thiếu cho cột số
# =========================

number_cols = [
    "bedrooms",
    "bathrooms",
    "floors",
    "frontage",
    "acces_road",
    "area_used",
    "floors_apartment",
    "year_built",
    "management_fee",
    "building_density"
]

for col in number_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df[col] = df[col].fillna(0)


# =========================
# 9. Xử lý dữ liệu thiếu cho cột chữ
# =========================

text_cols = [
    "project_name",
    "house_direction",
    "balcony_direction",
    "street",
    "ward",
    "city",
    "legal_status",
    "furniture_state",
    "seller_type",
    "post_type"
]

for col in text_cols:
    if col in df.columns:
        df[col] = df[col].fillna("Không rõ")


# =========================
# 10. Xử lý dữ liệu boolean
# =========================

boolean_cols = [
    "is_urgent",
    "has_garage",
    "has_pool",
    "has_elevator",
    "has_security",
    "has_parking",
    "has_swimming_pool",
    "has_gym",
    "has_supermarket"
]

for col in boolean_cols:
    if col in df.columns:
        df[col] = df[col].fillna(False)


# =========================
# 11. Xuất thống kê sau xử lý
# =========================

print("Dữ liệu sau preprocess:", df.shape)
print("Số dòng còn lại:", len(df))

print("\nKiểm tra dữ liệu thiếu:")
print(df.isnull().sum())

print("\n5 dòng đầu sau xử lý:")
print(df[["price", "price_vnd", "area", "area_clean", "price_per_m2_clean", "district"]].head())


# =========================
# Loại bỏ Outlier bằng IQR
# =========================

Q1 = df["price_per_m2_clean"].quantile(0.25)
Q3 = df["price_per_m2_clean"].quantile(0.75)

IQR = Q3 - Q1

lower = Q1 - 1.5 * IQR
upper = Q3 + 1.5 * IQR

print("Ngưỡng dưới:", lower)
print("Ngưỡng trên:", upper)

before = len(df)

df = df[
    (df["price_per_m2_clean"] >= lower) &
    (df["price_per_m2_clean"] <= upper)
]
df["price_per_m2_clean"] = df["price_per_m2_clean"].round(2)

after = len(df)

print("Đã loại:", before - after, "outlier")
# =========================
# 12. Lưu file sạch
# =========================

# CSV
csv_file = os.path.join(
    "output",
    "cleaned_bds_hcm.csv"
)

df.to_csv(
    csv_file,
    index=False,
    encoding="utf-8-sig"
)

# Excel
excel_file = os.path.join(
    "output",
    "cleaned_bds_hcm.xlsx"
)

df.to_excel(
    excel_file,
    index=False,
    engine="openpyxl"
)

print(f"\nĐã lưu CSV: {csv_file}")
print(f"Đã lưu Excel: {excel_file}")
