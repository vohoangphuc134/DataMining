import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# Cấu hình font chữ cho tiếng Việt
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Tahoma', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
sns.set_theme(style="whitegrid", rc={"axes.unicode_minus": False})

def main():
    print("Đang quét lỗi thiếu hụt (NaN) trên 3 website...")
    
    file_paths = {
        'Batdongsan.com.vn': 'output/data-batdongsan.csv',
        'Mogi.vn': 'output/data-mogi.csv',
        'nhadat.cafeland.vn': 'output/data-nhadat.csv'
    }
    
    dataframes = []
    for source, path in file_paths.items():
        if os.path.exists(path):
            df_temp = pd.read_csv(path)
            df_temp['Source'] = source
            dataframes.append(df_temp)
            
    if not dataframes:
        print("Lỗi: Không tìm thấy file dữ liệu CSV.")
        return
        
    df_raw = pd.concat(dataframes, ignore_index=True)

    # Các cột quan trọng cần soi xét
    cols_to_check = ['price', 'area', 'bedrooms', 'bathrooms']
    col_names_vn = {'price': 'Giá bán', 'area': 'Diện tích', 'bedrooms': 'Phòng ngủ', 'bathrooms': 'Phòng tắm'}
    
    # Tính tỷ lệ % NaN cho từng web và từng cột
    missing_data = []
    for source in file_paths.keys():
        df_src = df_raw[df_raw['Source'] == source]
        total_rows = len(df_src)
        
        for col in cols_to_check:
            # Đếm số dòng bị NaN
            nan_count = df_src[col].isna().sum()
            missing_pct = (nan_count / total_rows) * 100 if total_rows > 0 else 0
            
            missing_data.append({
                'Website': source,
                'Trường Thông Tin': col_names_vn[col],
                'Tỷ lệ Thiếu (%)': missing_pct
            })

    df_missing = pd.DataFrame(missing_data)

    # ==========================================
    # VẼ BIỂU ĐỒ SO SÁNH LỖI THIẾU HỤT (NaN)
    # ==========================================
    plt.figure(figsize=(12, 6))
    
    # Vẽ biểu đồ cột nhóm
    ax = sns.barplot(data=df_missing, x='Trường Thông Tin', y='Tỷ lệ Thiếu (%)', hue='Website', palette='Set2')
    
    plt.title('Biểu đồ: Tỷ lệ Bỏ trống Dữ liệu (NaN) giữa 3 Website', fontsize=16, fontweight='bold', pad=20)
    plt.ylabel('Tỷ lệ bị bỏ trống (%)', fontsize=12)
    plt.xlabel('Trường Thông Tin Quan Trọng', fontsize=12)
    plt.ylim(0, 100) # Thang đo từ 0 đến 100%
    
    # Đưa chú thích (Legend) ra bên ngoài góc phải cho gọn
    plt.legend(title='Nguồn Website', bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0.)

    # Ghi con số % hiển thị ngay trên đỉnh từng cột
    for p in ax.patches:
        height = p.get_height()
        if height > 0:
            ax.annotate(f'{height:.1f}%', 
                        (p.get_x() + p.get_width() / 2., height), 
                        ha='center', va='center', 
                        xytext=(0, 7), textcoords='offset points', 
                        fontsize=10, fontweight='bold', color='black')

    plt.tight_layout()
    print("Mở biểu đồ thành công! Bạn hãy chụp màn hình để đưa vào báo cáo nhé.")
    plt.show()

if __name__ == "__main__":
    main()