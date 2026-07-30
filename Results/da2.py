import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.mixture import GaussianMixture
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

sns.set_style("whitegrid")

# ----------------------------------------------------------------------
# 1. Load the data
# ----------------------------------------------------------------------
df = pd.read_csv(
    "Results/STOchastic/D2/Pop_200_N_10_Gen_60_D2_STO/nsga2_D_grid_ashp_pv_bess_tess/pareto_solutions.csv"
)

all_features = [
    "N_PV_hh",
    "E_BESS_cap_kwh",
    "E_TESS_cap_kwh",
    "annual_cost_total_eur",
    "annual_emissions_total_kg",
]

# ----------------------------------------------------------------------
# 2. PCA (kept on all 5 features -- this part is unchanged and still useful
#    for visualizing the overall trade-off structure)
# ----------------------------------------------------------------------
X_all = df[all_features]
scaler_all = StandardScaler()
X_all_scaled = scaler_all.fit_transform(X_all)

pca = PCA(n_components=2)
components = pca.fit_transform(X_all_scaled)
df["PC1"], df["PC2"] = components[:, 0], components[:, 1]

loadings = pd.DataFrame(pca.components_.T, columns=["PC1", "PC2"], index=all_features)
print("PCA Loadings (Weights of original features in each PC):")
print(loadings)
print("\nExplained variance ratio:")
print(pca.explained_variance_ratio_)

# ----------------------------------------------------------------------
# 3. Clustering to find design "phases"
#
#    IMPORTANT: we cluster on the DESIGN variables only (N_PV_hh,
#    E_BESS_cap_kwh, E_TESS_cap_kwh), not on cost/emissions. Cost and
#    emissions are *outputs* of the design -- they carry no independent
#    information, but their scale dominates distance-based clustering
#    and drowns out the actual discrete engineering switches we care
#    about (e.g. TESS on vs off).
#
#    We also use a Gaussian Mixture Model with diagonal covariance
#    instead of KMeans. Plain KMeans assumes round, equal-sized
#    clusters; the real phases here are long, thin, elongated sweeps
#    (a PV sweep, a BESS ramp), which KMeans cuts across rather than
#    around. A covariance-flexible GMM can stretch each cluster along
#    its own dominant axis.
# ----------------------------------------------------------------------
design_features = ["N_PV_hh", "E_BESS_cap_kwh", "E_TESS_cap_kwh"]
X_design = StandardScaler().fit_transform(df[design_features])

# For comparison/diagnostic purposes, show how plain KMeans behaves
# across k using silhouette score (same style as before).
sil_scores = {}
for k in range(2, 9):
    labels_k = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(X_design)
    sil_scores[k] = silhouette_score(X_design, labels_k)

# Fit the actual model we use for coloring: GMM with diagonal covariance,
# 4 components (matches the 4 known engineering regimes: TESS off/on x
# PV-sweep/BESS-ramp).
n_phases = 3
gmm = GaussianMixture(
    n_components=n_phases, covariance_type="diag", random_state=42, n_init=10
)
df["cluster"] = gmm.fit_predict(X_design).astype(str)

print(f"\nUsing GaussianMixture(n_components={n_phases}, covariance_type='diag')")
print("Cluster means (physical units):")
print(
    df.groupby("cluster")[
        design_features + ["annual_cost_total_eur", "annual_emissions_total_kg"]
    ]
    .mean()
    .round(2)
)
print("\nCluster sizes:")
print(df["cluster"].value_counts())

# ----------------------------------------------------------------------
# 4. Consistent color palette used across every plot
# ----------------------------------------------------------------------
cluster_order = sorted(df["cluster"].unique(), key=int)
palette = sns.color_palette("Set2", n_colors=len(cluster_order))
color_map = dict(zip(cluster_order, palette))

scatter_kwargs = dict(
    hue="cluster",
    hue_order=cluster_order,
    palette=color_map,
    s=45,
    edgecolor="black",
    linewidth=0.3,
    alpha=0.85,
)

# ----------------------------------------------------------------------
# 5. Plots: comparative, PCA, Pareto frontier, silhouette diagnostic
# ----------------------------------------------------------------------
fig, axes = plt.subplots(2, 2, figsize=(15, 12))

# --- Comparative Plot: BESS vs TESS, colored by phase ---
sns.scatterplot(
    data=df, x="E_TESS_cap_kwh", y="E_BESS_cap_kwh", ax=axes[0, 0], **scatter_kwargs
)
axes[0, 0].set_title("Comparative Plot: E_BESS_cap_kwh vs E_TESS_cap_kwh")
axes[0, 0].set_xlabel("Thermal Storage Capacity (E_TESS_cap_kwh)")
axes[0, 0].set_ylabel("Battery Storage Capacity (E_BESS_cap_kwh)")
axes[0, 0].grid(True, linestyle="--", alpha=0.6)

# --- PCA Plot, colored by phase ---
sns.scatterplot(data=df, x="PC1", y="PC2", ax=axes[0, 1], **scatter_kwargs)
axes[0, 1].set_title("PCA: First Two Principal Components")
axes[0, 1].set_xlabel(
    f"Principal Component 1 ({pca.explained_variance_ratio_[0]*100:.1f}% variance)"
)
axes[0, 1].set_ylabel(
    f"Principal Component 2 ({pca.explained_variance_ratio_[1]*100:.1f}% variance)"
)
axes[0, 1].grid(True, linestyle="--", alpha=0.6)

# --- Pareto frontier (cost vs emissions), colored by phase ---
sns.scatterplot(
    data=df,
    x="annual_cost_total_eur",
    y="annual_emissions_total_kg",
    ax=axes[1, 0],
    **scatter_kwargs,
)
axes[1, 0].set_title("Pareto Frontier, colored by design phase")
axes[1, 0].set_xlabel("Annual cost [EUR/year]")
axes[1, 0].set_ylabel("Annual emissions [kg CO2eq/year]")
axes[1, 0].grid(True, linestyle="--", alpha=0.6)

# --- Silhouette score vs k (KMeans on design vars, for reference only --
#     shown to illustrate why k=4 was chosen and why KMeans alone is a
#     weaker fit than the GMM used for the actual coloring above) ---
axes[1, 1].plot(
    list(sil_scores.keys()), list(sil_scores.values()), marker="o", color="#444444"
)
axes[1, 1].axvline(
    n_phases, color="crimson", linestyle="--", label=f"phases used: k={n_phases}"
)
axes[1, 1].set_title("KMeans silhouette score vs k (design vars)")
axes[1, 1].set_xlabel("Number of clusters (k)")
axes[1, 1].set_ylabel("Silhouette score")
axes[1, 1].legend()
axes[1, 1].grid(True, linestyle="--", alpha=0.6)

for ax in [axes[0, 0], axes[0, 1], axes[1, 0]]:
    ax.legend(title="Phase (cluster)", loc="best", fontsize=8)

plt.tight_layout()
plt.savefig("pareto_phase_analysis.png", dpi=150)
plt.show()
