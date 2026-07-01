"""
processing.py
=============
Module Processing Data – Dự án dự đoán giá bất động sản TP.HCM
Pipeline theo hướng dẫn của thầy:
  Ready Data
    1 Data Split / Sampling
    2 Feature Selection / Dimensionality Reduction
    3 Supervised Learning  (Regression: dự đoán price_vnd)
    4 Unsupervised Learning (Clustering + Anomaly Detection)
    5 Raw Metric
    6 Artifacts
    7 Metadata / Lineage  → Model Registry
"""

# -*- coding: utf-8 -*-
import sys, io
# Fix Windows terminal encoding (cp1252 -> utf-8)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import os
import json
import hashlib
import warnings
import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.model_selection import train_test_split, cross_val_score, KFold
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.feature_selection import mutual_info_regression, SelectKBest
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.cluster import KMeans, DBSCAN
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, r2_score,
    silhouette_score
)
from sklearn.decomposition import PCA
import joblib

warnings.filterwarnings("ignore")

# ===========================================================
# [CFG]  CẤU HÌNH 
# ===========================================================
RANDOM_SEED   = 42
INPUT_FILE    = os.path.join("output", "bds_hcm_selected_features.csv")
OUTPUT_DIR    = "output"
PLOT_DIR      = os.path.join(OUTPUT_DIR, "plots")
ARTIFACT_DIR  = os.path.join(OUTPUT_DIR, "artifacts")

TRAIN_RATIO   = 0.70
VAL_RATIO     = 0.15
TEST_RATIO    = 0.15          # = 1 - TRAIN - VAL
N_CLUSTERS    = 4             # K cho K-Means (có thể chỉnh qua Elbow)
TOP_K_FEATURES = 10           # Số feature giữ lại sau MI selection

np.random.seed(RANDOM_SEED)
for d in [PLOT_DIR, ARTIFACT_DIR]:
    os.makedirs(d, exist_ok=True)


# ===========================================================
# [UTIL]  HÀM TIỆN ÍCH
# ===========================================================
def log(msg: str):
    """In log có timestamp."""
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def dataset_hash(filepath: str) -> str:
    """MD5 hash của file input để ghi lineage."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def save_plot(fig, name: str):
    path = os.path.join(PLOT_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log(f"  [CHART] Đã lưu biểu đồ: {path}")


# ===========================================================
# [DOC]  ĐỌC DỮ LIỆU
# ===========================================================
log("=" * 60)
log("[DOC]  ĐỌC DỮ LIỆU ĐẦU VÀO")
log("=" * 60)

df = pd.read_csv(INPUT_FILE)
log(f"  Shape: {df.shape[0]} dòng × {df.shape[1]} cột")
log(f"  Các cột: {df.columns.tolist()}")

# Ghi hash để dùng cho Metadata sau
_hash = dataset_hash(INPUT_FILE)
log(f"  dataset_hash (MD5): {_hash}")


# ===========================================================
# [BUILD]  FEATURE ENGINEERING – tạo đặc trưng bổ sung trước khi split
# ===========================================================
log("\n" + "=" * 60)
log("[BUILD]  FEATURE ENGINEERING")
log("=" * 60)

df_fe = df.copy()

# Log-transform target (giảm skewness phân phối giá)
df_fe["log_price"] = np.log1p(df_fe["price_vnd"])

# Log-transform diện tích
df_fe["log_area"]  = np.log1p(df_fe["area_clean"])

# Giá trên m2 an toàn (tránh chia 0)
df_fe["price_per_m2_safe"] = df_fe["price_vnd"] / (df_fe["area_clean"] + 1)

# Tỉ lệ phòng ngủ / diện tích
if "bedrooms" in df_fe.columns:
    df_fe["bedroom_per_area"] = df_fe["bedrooms"] / (df_fe["area_clean"] + 1)

# Tổng số phòng (ngủ + tắm)
if "bedrooms" in df_fe.columns and "bathrooms" in df_fe.columns:
    df_fe["total_rooms"] = df_fe["bedrooms"] + df_fe["bathrooms"]

# Nhóm giá/m2 → 4 phân khúc thị trường (label encoding sau)
if "price_per_m2_clean" in df_fe.columns:
    df_fe["price_tier"] = pd.qcut(
        df_fe["price_per_m2_clean"],
        q=4,
        labels=["binh_dan", "trung_cap", "cao_cap", "luxury"]
    ).astype(str)

# Label Encoding các cột categorical
CAT_COLS = [c for c in
            ["property_type", "district", "legal_status",
             "furniture_state", "seller_type", "price_tier"]
            if c in df_fe.columns]

le_dict = {}
for col in CAT_COLS:
    le = LabelEncoder()
    df_fe[col + "_enc"] = le.fit_transform(df_fe[col].astype(str))
    le_dict[col] = le
    log(f"  Label encoded: {col}  ({df_fe[col].nunique()} lớp)")

log(f"  [OK] Feature Engineering xong. Shape: {df_fe.shape}")


# ===========================================================
# 1 DATA SPLIT / SAMPLING
# ===========================================================
log("\n" + "=" * 60)
log("1 DATA SPLIT / SAMPLING")
log("=" * 60)

# Tất cả feature số + encoded dùng cho model
FEATURE_COLS = (
    ["log_area", "price_per_m2_safe", "price_per_m2_clean"]
    + [c + "_enc" for c in CAT_COLS]
    + [c for c in ["bedrooms", "bathrooms", "floors", "frontage",
                   "acces_road", "bedroom_per_area", "total_rooms"]
       if c in df_fe.columns]
)
FEATURE_COLS = [c for c in FEATURE_COLS if c in df_fe.columns]

TARGET = "log_price"

X = df_fe[FEATURE_COLS].fillna(0)
y = df_fe[TARGET]

# Stratify theo price_tier_enc (4 lớp) thay vì property_type_enc (quá nhiều lớp hiếm)
def safe_stratify(col_name, df, min_count=2):
    if col_name not in df.columns:
        return None
    counts = df[col_name].value_counts()
    # Chỉ stratify nếu mọi class đều có >= 2 mẫu
    if (counts < min_count).any():
        return None
    return df[col_name]

stratify_col = safe_stratify("price_tier_enc", df_fe)

X_train, X_temp, y_train, y_temp = train_test_split(
    X, y,
    test_size=(VAL_RATIO + TEST_RATIO),
    random_state=RANDOM_SEED,
    stratify=stratify_col
)

# Tách val / test từ tập temp (tỉ lệ 50/50 của temp = 15%/15% tổng)
stratify_temp = safe_stratify("price_tier_enc", df_fe.loc[X_temp.index])
X_val, X_test, y_val, y_test = train_test_split(
    X_temp, y_temp,
    test_size=0.50,
    random_state=RANDOM_SEED,
    stratify=stratify_temp
)

log(f"  Train : {X_train.shape[0]} mẫu ({X_train.shape[0]/len(X)*100:.1f}%)")
log(f"  Val   : {X_val.shape[0]} mẫu  ({X_val.shape[0]/len(X)*100:.1f}%)")
log(f"  Test  : {X_test.shape[0]} mẫu  ({X_test.shape[0]/len(X)*100:.1f}%)")
log(f"  Features: {FEATURE_COLS}")

# Biểu đồ phân phối giá theo tập
fig, ax = plt.subplots(figsize=(9, 4))
for label, y_part, color in [("Train", y_train, "#4C72B0"),
                               ("Val",   y_val,   "#DD8452"),
                               ("Test",  y_test,  "#55A868")]:
    ax.hist(np.expm1(y_part) / 1e9, bins=40, alpha=0.55,
            label=label, color=color, edgecolor="white")
ax.set_xlabel("Giá (tỷ VNĐ)")
ax.set_ylabel("Số lượng")
ax.set_title("Phân phối giá trong 3 tập Train / Val / Test")
ax.legend()
save_plot(fig, "01_split_distribution.png")


# ===========================================================
# 2 FEATURE SELECTION / DIMENSIONALITY REDUCTION
# ===========================================================
log("\n" + "=" * 60)
log("2 FEATURE SELECTION / DIMENSIONALITY REDUCTION")
log("=" * 60)

# ---- 2a. Correlation filter: loại feature tương quan cao với nhau ----
corr_matrix = X_train.corr().abs()
upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
high_corr_cols = [col for col in upper.columns if any(upper[col] > 0.85)]
log(f"  Multicollinearity (>0.85) → loại: {high_corr_cols}")

X_train_fs = X_train.drop(columns=high_corr_cols, errors="ignore")
X_val_fs   = X_val.drop(columns=high_corr_cols, errors="ignore")
X_test_fs  = X_test.drop(columns=high_corr_cols, errors="ignore")

# Biểu đồ correlation matrix
fig, ax = plt.subplots(figsize=(11, 9))
sns.heatmap(corr_matrix, annot=False, cmap="coolwarm", ax=ax,
            linewidths=0.3, linecolor="white")
ax.set_title("Ma trận tương quan features")
save_plot(fig, "02_correlation_matrix.png")

# ---- 2b. Mutual Information: xếp hạng mức độ ảnh hưởng đến price ----
mi_scores = mutual_info_regression(X_train_fs, y_train, random_state=RANDOM_SEED)
mi_df = pd.DataFrame({"feature": X_train_fs.columns, "mi_score": mi_scores})
mi_df = mi_df.sort_values("mi_score", ascending=False).reset_index(drop=True)
log("\n  Mutual Information với log_price (top 10):")
log(mi_df.head(10).to_string(index=False))

# Giữ top K feature theo MI
k = min(TOP_K_FEATURES, len(mi_df))
selected_features = mi_df.head(k)["feature"].tolist()
log(f"\n  [OK] Features được chọn ({k}): {selected_features}")

X_train_sel = X_train_fs[selected_features]
X_val_sel   = X_val_fs[selected_features]
X_test_sel  = X_test_fs[selected_features]

# Biểu đồ MI scores
fig, ax = plt.subplots(figsize=(9, 5))
mi_df.set_index("feature")["mi_score"].head(k).sort_values().plot(
    kind="barh", ax=ax, color="#4C72B0", edgecolor="white")
ax.set_title(f"Mutual Information Score (top {k} features)")
ax.set_xlabel("MI Score")
save_plot(fig, "03_mutual_information.png")

# ---- 2c. PCA – chỉ lưu biểu đồ explained variance, không bắt buộc dùng ----
scaler_pca = StandardScaler()
X_pca_data = scaler_pca.fit_transform(X_train_sel)
pca = PCA(random_state=RANDOM_SEED)
pca.fit(X_pca_data)
cumvar = np.cumsum(pca.explained_variance_ratio_)
n_pca_95 = np.argmax(cumvar >= 0.95) + 1

fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(range(1, len(cumvar) + 1), cumvar, marker="o", color="#4C72B0")
ax.axhline(0.95, color="#DD8452", linestyle="--", label="95% variance")
ax.axvline(n_pca_95, color="#55A868", linestyle="--",
           label=f"{n_pca_95} components → 95%")
ax.set_xlabel("Số lượng components")
ax.set_ylabel("Cumulative explained variance")
ax.set_title("PCA – Explained Variance")
ax.legend()
save_plot(fig, "04_pca_explained_variance.png")
log(f"  PCA: cần {n_pca_95} components để đạt 95% variance  "
    f"(dùng MI selection thay vì PCA cho khả năng giải thích tốt hơn)")

# Scale dữ liệu cho linear models
scaler = StandardScaler()
X_train_sc = scaler.fit_transform(X_train_sel)
X_val_sc   = scaler.transform(X_val_sel)
X_test_sc  = scaler.transform(X_test_sel)


# ===========================================================
# 3 SUPERVISED LEARNING – REGRESSION
# ===========================================================
log("\n" + "=" * 60)
log("3 SUPERVISED LEARNING – DỰ ĐOÁN GIÁ (REGRESSION)")
log("=" * 60)

# ---- Định nghĩa các mô hình ----
MODELS = {
    "Ridge Regression": {
        "model": Ridge(alpha=10),
        "scaled": True,
        "params": {"alpha": 10}
    },
    "Random Forest": {
        "model": RandomForestRegressor(
            n_estimators=300, max_depth=12, min_samples_leaf=5,
            random_state=RANDOM_SEED, n_jobs=-1
        ),
        "scaled": False,
        "params": {"n_estimators": 300, "max_depth": 12, "min_samples_leaf": 5}
    },
    "Gradient Boosting": {
        "model": GradientBoostingRegressor(
            n_estimators=300, max_depth=5, learning_rate=0.05,
            subsample=0.8, random_state=RANDOM_SEED
        ),
        "scaled": False,
        "params": {"n_estimators": 300, "max_depth": 5,
                   "learning_rate": 0.05, "subsample": 0.8}
    },
}

results      = []
trained_models = {}

for name, cfg in MODELS.items():
    model = cfg["model"]
    Xtr   = X_train_sc if cfg["scaled"] else X_train_sel.values
    Xvl   = X_val_sc   if cfg["scaled"] else X_val_sel.values
    Xts   = X_test_sc  if cfg["scaled"] else X_test_sel.values

    # Train
    model.fit(Xtr, y_train)

    # Predict trên Val (tune) và Test (final)
    y_pred_val_log  = model.predict(Xvl)
    y_pred_test_log = model.predict(Xts)

    # Chuyển về giá thật (VNĐ)
    y_val_real       = np.expm1(y_val)
    y_pred_val_real  = np.expm1(y_pred_val_log)
    y_test_real      = np.expm1(y_test)
    y_pred_test_real = np.expm1(y_pred_test_log)

    # ---- Raw Metric (tính ngay sau mỗi model) ----
    mae_val   = mean_absolute_error(y_val_real,  y_pred_val_real)
    rmse_val  = np.sqrt(mean_squared_error(y_val_real, y_pred_val_real))
    r2_val    = r2_score(y_val,  y_pred_val_log)

    mae_test  = mean_absolute_error(y_test_real, y_pred_test_real)
    rmse_test = np.sqrt(mean_squared_error(y_test_real, y_pred_test_real))
    r2_test   = r2_score(y_test, y_pred_test_log)

    # Cross-validation trên tập train (5-fold)
    cv_scores = cross_val_score(
        model, Xtr, y_train,
        cv=KFold(n_splits=5, shuffle=True, random_state=RANDOM_SEED),
        scoring="r2"
    )

    results.append({
        "model"        : name,
        "val_MAE_ty"   : round(mae_val  / 1e9, 3),
        "val_RMSE_ty"  : round(rmse_val / 1e9, 3),
        "val_R2"       : round(r2_val,  4),
        "test_MAE_ty"  : round(mae_test  / 1e9, 3),
        "test_RMSE_ty" : round(rmse_test / 1e9, 3),
        "test_R2"      : round(r2_test, 4),
        "cv_R2_mean"   : round(cv_scores.mean(), 4),
        "cv_R2_std"    : round(cv_scores.std(),  4),
    })
    trained_models[name] = model

    log(f"\n  [{name}]")
    log(f"    Val  → MAE={mae_val/1e9:.3f} tỷ | RMSE={rmse_val/1e9:.3f} tỷ | R²={r2_val:.4f}")
    log(f"    Test → MAE={mae_test/1e9:.3f} tỷ | RMSE={rmse_test/1e9:.3f} tỷ | R²={r2_test:.4f}")
    log(f"    CV-5 R² = {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

df_results = pd.DataFrame(results)

# ---- Chọn mô hình tốt nhất theo test_R2 ----
best_row   = df_results.sort_values("test_R2", ascending=False).iloc[0]
best_name  = best_row["model"]
best_model = trained_models[best_name]
log(f"\n  [BEST] Mô hình tốt nhất: {best_name}  (test R²={best_row['test_R2']})")

# ---- Biểu đồ so sánh mô hình ----
fig, axes = plt.subplots(1, 3, figsize=(14, 5))
metrics = [("test_R2", "R² (Test)"), ("test_MAE_ty", "MAE (tỷ VNĐ)"),
           ("test_RMSE_ty", "RMSE (tỷ VNĐ)")]
colors   = ["#4C72B0", "#DD8452", "#C44E52"]
for ax, (col, label), color in zip(axes, metrics, colors):
    ax.bar(df_results["model"], df_results[col], color=color, edgecolor="white")
    ax.set_title(label)
    ax.set_xticklabels(df_results["model"], rotation=20, ha="right", fontsize=9)
    for i, v in enumerate(df_results[col]):
        ax.text(i, v + 0.001, str(v), ha="center", fontsize=8)
plt.suptitle("So sánh Raw Metric giữa các mô hình (tập Test)", fontsize=12)
plt.tight_layout()
save_plot(fig, "05_model_comparison.png")

# ---- Predicted vs Actual (mô hình tốt nhất) ----
Xts_best = X_test_sc if MODELS[best_name]["scaled"] else X_test_sel.values
y_pred_best_log  = best_model.predict(Xts_best)
y_pred_best_real = np.expm1(y_pred_best_log)
y_test_real      = np.expm1(y_test)

fig, ax = plt.subplots(figsize=(7, 7))
ax.scatter(y_test_real / 1e9, y_pred_best_real / 1e9,
           alpha=0.3, s=12, color="#4C72B0", edgecolors="none")
lim = max(y_test_real.max(), y_pred_best_real.max()) / 1e9 * 1.05
ax.plot([0, lim], [0, lim], "r--", linewidth=1.5, label="Perfect prediction")
ax.set_xlabel("Giá thực (tỷ VNĐ)")
ax.set_ylabel("Giá dự đoán (tỷ VNĐ)")
ax.set_title(f"Predicted vs Actual – {best_name}")
ax.legend()
save_plot(fig, "06_predicted_vs_actual.png")

# ---- Feature Importance (nếu là tree-based) ----
if hasattr(best_model, "feature_importances_"):
    fi = pd.Series(best_model.feature_importances_, index=selected_features)
    fi_sorted = fi.sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(9, 5))
    fi_sorted.plot(kind="bar", ax=ax, color="#55A868", edgecolor="white")
    ax.set_title(f"Feature Importance – {best_name}")
    ax.set_ylabel("Importance")
    ax.set_xticklabels(fi_sorted.index, rotation=40, ha="right", fontsize=9)
    save_plot(fig, "07_feature_importance.png")

    log("\n  Feature Importance:")
    for feat, score in fi_sorted.items():
        log(f"    {feat:<30} {score:.4f}")


# ===========================================================
# 4 UNSUPERVISED LEARNING
# ===========================================================
log("\n" + "=" * 60)
log("4 UNSUPERVISED LEARNING – PHÂN CỤM & PHÁT HIỆN BẤT THƯỜNG")
log("=" * 60)

# Dữ liệu cho clustering: diện tích + giá/m2 (scale trước)
cluster_features = ["area_clean", "price_per_m2_clean"]
cluster_features = [c for c in cluster_features if c in df_fe.columns]
X_cluster = df_fe[cluster_features].fillna(0)

scaler_clust = StandardScaler()
X_cluster_sc = scaler_clust.fit_transform(X_cluster)

# ---- Elbow Method chọn K tối ưu ----
inertia_list = []
K_range = range(2, 11)
for k_val in K_range:
    km_tmp = KMeans(n_clusters=k_val, random_state=RANDOM_SEED, n_init=10)
    km_tmp.fit(X_cluster_sc)
    inertia_list.append(km_tmp.inertia_)

fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(list(K_range), inertia_list, marker="o", color="#4C72B0")
ax.axvline(N_CLUSTERS, color="#DD8452", linestyle="--",
           label=f"K={N_CLUSTERS} (chọn)")
ax.set_xlabel("Số cụm K")
ax.set_ylabel("Inertia (WCSS)")
ax.set_title("Elbow Method – chọn K cho K-Means")
ax.legend()
save_plot(fig, "08_kmeans_elbow.png")

# ---- K-Means với K đã chọn ----
kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_SEED, n_init=20)
df_fe["cluster_kmeans"] = kmeans.fit_predict(X_cluster_sc)

sil_kmeans = silhouette_score(X_cluster_sc, df_fe["cluster_kmeans"])
log(f"  K-Means (K={N_CLUSTERS}) → Silhouette Score = {sil_kmeans:.4f}")
log(f"  Phân bố cụm:\n{df_fe['cluster_kmeans'].value_counts().sort_index().to_string()}")

# Gán nhãn phân khúc dựa trên giá/m2 trung bình của mỗi cụm
cluster_summary = (
    df_fe.groupby("cluster_kmeans")[["price_per_m2_clean", "area_clean", "price_vnd"]]
    .median()
    .sort_values("price_per_m2_clean")
    .reset_index()
)
tier_labels = ["Bình dân", "Trung cấp", "Cao cấp", "Luxury"][:N_CLUSTERS]
cluster_summary["tier"] = tier_labels
cluster_map = dict(zip(cluster_summary["cluster_kmeans"], cluster_summary["tier"]))
df_fe["cluster_tier"] = df_fe["cluster_kmeans"].map(cluster_map)
log(f"\n  Cluster summary:\n{cluster_summary.to_string(index=False)}")

# Biểu đồ scatter các cụm
fig, ax = plt.subplots(figsize=(9, 6))
colors_clust = ["#4C72B0", "#DD8452", "#55A868", "#C44E52"]
for cid in sorted(df_fe["cluster_kmeans"].unique()):
    mask = df_fe["cluster_kmeans"] == cid
    ax.scatter(
        df_fe.loc[mask, "area_clean"],
        df_fe.loc[mask, "price_per_m2_clean"] / 1e6,
        alpha=0.4, s=8,
        color=colors_clust[cid % len(colors_clust)],
        label=f"Cụm {cid}: {cluster_map.get(cid, '')}"
    )
ax.set_xlabel("Diện tích (m²)")
ax.set_ylabel("Giá/m² (triệu VNĐ)")
ax.set_title("K-Means Clustering – Phân cụm BĐS theo phân khúc")
ax.legend(markerscale=3)
save_plot(fig, "09_kmeans_clusters.png")

# ---- DBSCAN – Phát hiện tin đăng bất thường ----
dbscan = DBSCAN(eps=0.5, min_samples=10)
df_fe["dbscan_label"] = dbscan.fit_predict(X_cluster_sc)

n_outliers = (df_fe["dbscan_label"] == -1).sum()
n_normal   = (df_fe["dbscan_label"] != -1).sum()
log(f"\n  DBSCAN → {n_outliers} outlier ({n_outliers/len(df_fe)*100:.1f}%) | "
    f"{n_normal} điểm bình thường")

fig, ax = plt.subplots(figsize=(9, 6))
mask_norm = df_fe["dbscan_label"] != -1
mask_out  = df_fe["dbscan_label"] == -1
ax.scatter(df_fe.loc[mask_norm, "area_clean"],
           df_fe.loc[mask_norm, "price_per_m2_clean"] / 1e6,
           alpha=0.3, s=6, color="#4C72B0", label="Bình thường")
ax.scatter(df_fe.loc[mask_out,  "area_clean"],
           df_fe.loc[mask_out,  "price_per_m2_clean"] / 1e6,
           alpha=0.7, s=18, color="#C44E52", marker="x", label="Outlier")
ax.set_xlabel("Diện tích (m²)")
ax.set_ylabel("Giá/m² (triệu VNĐ)")
ax.set_title("DBSCAN – Phát hiện tin đăng bất thường")
ax.legend()
save_plot(fig, "10_dbscan_anomaly.png")


# ===========================================================
# 5 RAW METRIC – TỔNG KẾT
# ===========================================================
log("\n" + "=" * 60)
log("5 RAW METRIC – TỔNG KẾT")
log("=" * 60)

print("\n" + "=" * 70)
print(f"{'Model':<22} {'Val R²':>8} {'Test R²':>8} "
      f"{'MAE(tỷ)':>10} {'RMSE(tỷ)':>10} {'CV R²':>12}")
print("-" * 70)
for _, row in df_results.iterrows():
    print(f"{row['model']:<22} {row['val_R2']:>8} {row['test_R2']:>8} "
          f"{row['test_MAE_ty']:>10} {row['test_RMSE_ty']:>10} "
          f"{row['cv_R2_mean']:>6.4f}±{row['cv_R2_std']:.4f}")
print(f"\n  Silhouette Score K-Means = {sil_kmeans:.4f}")
print(f"  DBSCAN Outlier rate      = {n_outliers/len(df_fe)*100:.2f}%")
print("=" * 70)

# Lưu bảng kết quả
df_results.to_csv(os.path.join(ARTIFACT_DIR, "raw_metrics.csv"),
                  index=False, encoding="utf-8-sig")
log("  [OK] Đã lưu raw_metrics.csv")


# ===========================================================
# 6 ARTIFACTS
# ===========================================================
log("\n" + "=" * 60)
log("6 ARTIFACTS – LƯU MÔ HÌNH & DỮ LIỆU")
log("=" * 60)

# Mô hình supervised
joblib.dump(best_model,        os.path.join(ARTIFACT_DIR, "best_model.pkl"))
joblib.dump(scaler,            os.path.join(ARTIFACT_DIR, "scaler.pkl"))
joblib.dump(le_dict,           os.path.join(ARTIFACT_DIR, "label_encoders.pkl"))

# Mô hình unsupervised
joblib.dump(kmeans,            os.path.join(ARTIFACT_DIR, "kmeans_model.pkl"))
joblib.dump(scaler_clust,      os.path.join(ARTIFACT_DIR, "scaler_cluster.pkl"))
joblib.dump(dbscan,            os.path.join(ARTIFACT_DIR, "dbscan_model.pkl"))

# Danh sách features đã chọn
with open(os.path.join(ARTIFACT_DIR, "selected_features.json"), "w",
          encoding="utf-8") as f:
    json.dump({"selected_features": selected_features,
               "target": TARGET,
               "cat_cols_encoded": CAT_COLS}, f, ensure_ascii=False, indent=2)

# Dữ liệu đã gắn nhãn cluster
cluster_out_cols = ["price_vnd", "area_clean", "price_per_m2_clean",
                    "district", "property_type",
                    "cluster_kmeans", "cluster_tier", "dbscan_label"]
cluster_out_cols += [f for f in selected_features if f not in cluster_out_cols]
cluster_out_cols = [c for c in cluster_out_cols if c in df_fe.columns]
df_fe[cluster_out_cols].to_csv(
    os.path.join(ARTIFACT_DIR, "cluster_labels.csv"),
    index=False, encoding="utf-8-sig"
)

# Xuat them xlsx de de xem
df_fe[cluster_out_cols].to_excel(
    os.path.join(ARTIFACT_DIR, "cluster_labels.xlsx"),
    index=False, sheet_name="Cluster_Labels", engine="openpyxl"
)
log("  [OK] Da luu cluster_labels.csv + cluster_labels.xlsx")

log(f"  [OK] Đã lưu tất cả artifacts vào: {ARTIFACT_DIR}/")
for f in os.listdir(ARTIFACT_DIR):
    log(f"     {f}")


# ===========================================================
# 7 METADATA / LINEAGE
# ===========================================================
log("\n" + "=" * 60)
log("7 METADATA / LINEAGE → MODEL REGISTRY")
log("=" * 60)

metadata = {
    "project"         : "Dự đoán giá bất động sản TP.HCM",
    "version"         : "1.0.0",
    "timestamp"       : datetime.datetime.now().isoformat(),

    # Lineage – truy vết dữ liệu
    "lineage": {
        "input_file"      : INPUT_FILE,
        "dataset_hash_md5": _hash,
        "n_total_samples" : len(df),
        "n_train"         : len(X_train),
        "n_val"           : len(X_val),
        "n_test"          : len(X_test),
    },

    # Config
    "config": {
        "random_seed"     : RANDOM_SEED,
        "train_ratio"     : TRAIN_RATIO,
        "val_ratio"       : VAL_RATIO,
        "test_ratio"      : TEST_RATIO,
        "n_clusters"      : N_CLUSTERS,
        "top_k_features"  : TOP_K_FEATURES,
        "stratify_by"     : "property_type_enc",
    },

    # Supervised – mô hình tốt nhất
    "best_supervised_model": {
        "name"            : best_name,
        "hyperparameters" : MODELS[best_name]["params"],
        "selected_features": selected_features,
        "val_R2"          : float(best_row["val_R2"]),
        "test_R2"         : float(best_row["test_R2"]),
        "test_MAE_ty"     : float(best_row["test_MAE_ty"]),
        "test_RMSE_ty"    : float(best_row["test_RMSE_ty"]),
        "cv_R2_mean"      : float(best_row["cv_R2_mean"]),
        "cv_R2_std"       : float(best_row["cv_R2_std"]),
        "artifact"        : "artifacts/best_model.pkl",
    },

    # Unsupervised
    "unsupervised": {
        "kmeans": {
            "k"               : N_CLUSTERS,
            "silhouette_score": round(float(sil_kmeans), 4),
            "cluster_tiers"   : cluster_map,
            "artifact"        : "artifacts/kmeans_model.pkl",
        },
        "dbscan": {
            "eps"             : 0.5,
            "min_samples"     : 10,
            "n_outliers"      : int(n_outliers),
            "outlier_rate_pct": round(n_outliers / len(df_fe) * 100, 2),
            "artifact"        : "artifacts/dbscan_model.pkl",
        },
    },

    # Tất cả kết quả models
     "all_models_results": df_results.to_dict(orient="records"),

    # MI scores – dùng cho visualize_processing.py (biểu đồ P4)
    "mutual_information": mi_df[["feature", "mi_score"]].to_dict(orient="records"),

    # Elbow inertia – dùng cho visualize_processing.py (biểu đồ P5)
    "elbow_inertia": [
        {"k": int(k_val), "inertia": round(float(inertia), 2)}
        for k_val, inertia in zip(K_range, inertia_list)
    ],
}

metadata_path = os.path.join(ARTIFACT_DIR, "metadata.json")
with open(metadata_path, "w", encoding="utf-8") as f:
    json.dump(metadata, f, ensure_ascii=False, indent=2)

log(f"  [OK] metadata.json đã lưu tại: {metadata_path}")
log(f"\n  Nội dung tóm tắt:")
log(f"    version        : {metadata['version']}")
log(f"    timestamp      : {metadata['timestamp']}")
log(f"    dataset_hash   : {_hash}")
log(f"    best model     : {best_name}  R²={best_row['test_R2']}")
log(f"    silhouette     : {sil_kmeans:.4f}")
log(f"    outlier rate   : {n_outliers/len(df_fe)*100:.2f}%")



# ===========================================================
# [DONE]  HOÀN THÀNH
# ===========================================================
log("\n" + "=" * 60)
log("[DONE]  PROCESSING PIPELINE HOÀN THÀNH")
log("=" * 60)
log(f"  [DIR] Artifacts : {ARTIFACT_DIR}/")
log(f"  [CHART] Plots     : {PLOT_DIR}/")
log(f"  [FILE] Metadata  : {metadata_path}")
