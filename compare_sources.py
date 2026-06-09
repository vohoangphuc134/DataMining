import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os
import numpy as np

# Cấu hình hiển thị tiếng Việt và style cho biểu đồ
plt.rcParams['font.family'] = 'sans-serif'
sns.set_theme(style="whitegrid", palette="pastel")

def main():
    # Định nghĩa các file và tên nguồn (Website)
    file_info = [
        {'path': 'output/data-batdongsan.csv', 'source_name': 'Batdongsan.com.vn'},
        {'path': 'output/data-mogi.csv', 'source_name': 'Mogi.vn'},
        {'path': 'output/data-nhadat.csv', 'source_name': 'nhadat.cafeland.vn'}
    ]
    
    dataframes = []
    
    # 1. Đọc và dán nhãn nguồn gốc dữ liệu
    print("Đang tải dữ liệu từ các nguồn...")
    for info in file_info:
        if os.path.exists(info['path']):
            try:
                df_temp = pd.read_csv(info['path'])
                # Ghi đè tên nguồn cho chắc chắn
                df_temp['website_source'] = info['source_name']
                dataframes.append(df_temp)
            except Exception as e:
                print(f"Lỗi đọc file {info['path']}: {e}")
        else:
            print(f"[CẢNH BÁO] Không tìm thấy file: {info['path']}")

    if not dataframes:
        print("Không có dữ liệu. Kết thúc.")
        return

    # Gộp tất cả thành 1 bảng dữ liệu duy nhất
    df = pd.concat(dataframes, ignore_index=True)
    
    # Để tính toán chất lượng dữ liệu, ta đếm tỷ lệ trống của cột Area trước khi xoá
    # Tính tỷ lệ % bài đăng CÓ nhập Diện tích (Area không bị NaN)
    quality_df = df.groupby('website_source').apply(
        lambda x: pd.Series({
            'total_posts': len(x),
            'has_area_pct': (x['area'].notna().sum() / len(x)) * 100,
            'has_bedroom_pct': (x['bedrooms'].notna().sum() / len(x)) * 100
        })
    ).reset_index()

    # 2. LÀM SẠCH DỮ LIỆU ĐỂ VẼ SO SÁNH GIÁ
    df_clean = df.dropna(subset=['price', 'area']).copy()
    df_clean = df_clean[(df_clean['area'] < 300) & (df_clean['price'] < 30000) & (df_clean['price'] > 500)]

    # ==========================
    # BẮT ĐẦU VẼ BIỂU ĐỒ (MỖI BIỂU ĐỒ 1 TRANG/CỬA SỔ)
    # ==========================

    # Biểu đồ 1: Số lượng tin cào được từ mỗi trang
    plt.figure(figsize=(10, 6))
    ax1 = sns.barplot(data=quality_df, x='website_source', y='total_posts', hue='website_source', palette='Set2', legend=False)
    plt.title('Tổng số lượng tin cào được', fontsize=15, fontweight='bold')
    plt.ylabel('Số lượng tin')
    plt.xlabel('Nguồn Website')
    # Thêm số liệu lên cột
    for p in ax1.patches:
        ax1.annotate(f'{int(p.get_height())}', (p.get_x() + p.get_width() / 2., p.get_height()), ha='center', va='center', xytext=(0, 5), textcoords='offset points')
    plt.tight_layout()

    # Biểu đồ 2: Đánh giá Chất lượng dữ liệu (% tin có nhập Diện tích đầy đủ)
    plt.figure(figsize=(10, 6))
    ax2 = sns.barplot(data=quality_df, x='website_source', y='has_area_pct', hue='website_source', palette='Set1', legend=False)
    plt.title('Chất lượng tin đăng (% tin có nhập Diện tích)', fontsize=15, fontweight='bold')
    plt.ylabel('Tỷ lệ phần trăm (%)')
    plt.xlabel('Nguồn Website')
    plt.ylim(0, 110)
    for p in ax2.patches:
        ax2.annotate(f'{p.get_height():.1f}%', (p.get_x() + p.get_width() / 2., p.get_height()), ha='center', va='center', xytext=(0, 5), textcoords='offset points')
    plt.tight_layout()

    # Biểu đồ 3: So sánh Giá/m2 giữa các Web (Boxplot)
    plt.figure(figsize=(10, 6))
    sns.boxplot(data=df_clean, x='website_source', y='price_per_m2', hue='website_source', palette='pastel', legend=False)
    plt.title('So sánh Mức Giá/m2 Đăng bán giữa các Web\n(Nhìn ra web nào hay đăng giá rẻ ảo)', fontsize=15, fontweight='bold')
    plt.ylabel('Giá / m2 (Triệu VNĐ)')
    plt.xlabel('Nguồn Website')
    plt.tight_layout()
    
    print("Đang hiển thị 3 biểu đồ trên 3 cửa sổ riêng biệt...")
    plt.show()

if __name__ == '__main__':
    main()
