import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# Cấu hình
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Tahoma', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
sns.set_theme(style="whitegrid", rc={"axes.unicode_minus": False})

def clean_district(address):
    if not isinstance(address, str): return None
    addr = address.lower()
    districts = [
        "quận 1", "quận 2", "quận 3", "quận 4", "quận 5", "quận 6", "quận 7", "quận 8", 
        "quận 9", "quận 10", "quận 11", "quận 12",
        "bình tân", "bình thạnh", "gò vấp", "phú nhuận", "tân bình", "tân phú",
        "thủ đức", "bình chánh", "cần giờ", "củ chi", "hóc môn", "nhà bè"
    ]
    for d in districts:
        if d in addr:
            if d in ["quận 2", "quận 9", "thủ đức"]: return "TP. Thủ Đức"
            return d.title()
    return None

def main():
    print("Đang vẽ các Biểu đồ Cột theo yêu cầu...")
    files = ['output/data-batdongsan.csv', 'output/data-mogi.csv', 'output/data-nhadat.csv']
    dfs = []
    for f in files:
        if os.path.exists(f): dfs.append(pd.read_csv(f))
    df = pd.concat(dfs, ignore_index=True)

    df_clean = df.dropna(subset=['price', 'area', 'address_full']).copy()
    df_clean = df_clean[(df_clean['price'] > 500) & (df_clean['price'] < 30000) & 
                        (df_clean['area'] < 300) & (df_clean['area'] >= 20)].copy()
    
    df_clean['price_per_m2'] = df_clean['price'] / df_clean['area']
    df_clean['district'] = df_clean['address_full'].apply(clean_district)
    df_clean = df_clean.dropna(subset=['district'])

    # ==========================================
    # Biểu đồ 1. Số lượng nhà theo Quận
    # ==========================================
    plt.figure("Biểu đồ Cột 1", figsize=(12, 6))
    district_counts = df_clean['district'].value_counts()
    ax1 = sns.barplot(x=district_counts.index, y=district_counts.values, palette="Blues_r")
    plt.title('Số lượng Căn hộ đang bán theo từng Khu vực', fontsize=16, fontweight='bold', pad=15)
    plt.xticks(rotation=45, ha='right')
    plt.ylabel('Số lượng (căn)')
    for p in ax1.patches:
        ax1.annotate(f'{int(p.get_height())}', (p.get_x() + p.get_width() / 2., p.get_height()), ha='center', va='bottom', xytext=(0, 5), textcoords='offset points')

    # ==========================================
    # Biểu đồ 2. Giá/m2 trung bình theo Quận (Horizontal)
    # ==========================================
    plt.figure("Biểu đồ Cột 2", figsize=(12, 8))
    avg_price = df_clean.groupby('district')['price_per_m2'].median().sort_values(ascending=False)
    ax2 = sns.barplot(x=avg_price.values, y=avg_price.index, palette="Reds_r")
    plt.title('Mức Giá / m2 Trung bình theo từng Khu vực', fontsize=16, fontweight='bold', pad=15)
    plt.xlabel('Giá (Triệu VNĐ/m2)')
    for i, v in enumerate(avg_price.values):
        ax2.text(v + 1, i, f"{v:.1f}", color='black', va='center')

    print("Hoàn tất vẽ 2 biểu đồ cột!")
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()
