import pandas as pd
import os

# =========================
# 1. Đọc file đã tiền xử lý
# =========================

input_file = os.path.join("output", "cleaned_bds_hcm.csv")

df = pd.read_csv(input_file)

print("Dữ liệu sau preprocessing:", df.shape)
print("Các cột hiện có:")
print(df.columns.tolist())


# =========================
# 2. Chọn các thuộc tính quan trọng
# =========================

selected_cols = [
    "property_type",
    "district",
    "price_vnd",
    "area_clean",
    "price_per_m2_clean",
    "bedrooms",
    "bathrooms",
    "floors",
    "frontage",
    "acces_road",
    "legal_status",
    "furniture_state",
    "seller_type"
]

# Chỉ lấy những cột thật sự tồn tại
selected_cols = [
    col for col in selected_cols
    if col in df.columns
]

df_selected = df[selected_cols]


# =========================
# 3. Kiểm tra dữ liệu sau chọn thuộc tính
# =========================

print("\nDữ liệu sau Feature Selection:", df_selected.shape)

print("\nCác cột được giữ lại:")
print(df_selected.columns.tolist())

print("\nKiểm tra dữ liệu thiếu:")
print(df_selected.isnull().sum())

print("\n5 dòng đầu:")
print(df_selected.head())


# =========================
# 4. Lưu file sau Feature Selection
# =========================

output_file = os.path.join("output", "bds_hcm_selected_features.csv")

df_selected.to_csv(
    output_file,
    index=False,
    encoding="utf-8-sig"
)

print(f"\nĐã lưu file: {output_file}")