import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.mixture import GaussianMixture

sns.set_style("whitegrid")

# ----------------------------------------------------------------------
# 1. Load the data
# ----------------------------------------------------------------------
df = pd.read_csv(
    "/home/pesim/uni/lukas/Neighborhood_Multi-Energy_Microgrid_System/Results/STOchastic/D2/Pop_200_N_100_Gen_60_D2_STO/nsga2_C_grid_eb_pv_bess/pareto_solutions.csv"
)

all_features = [
    "N_PV_hh",
    "E_BESS_cap_kwh",
    # "E_TESS_cap_kwh",
    "annual_cost_total_eur",
    "annual_emissions_total_kg",
]
# design_features = ["N_PV_hh", "E_BESS_cap_kwh", "E_TESS_cap_kwh"]
design_features = ["N_PV_hh", "E_BESS_cap_kwh"]

# ----------------------------------------------------------------------
# 2. PCA (on all 5 features -- overall trade-off structure)
# ----------------------------------------------------------------------
X_all_scaled = StandardScaler().fit_transform(df[all_features])
pca = PCA(n_components=2)
components = pca.fit_transform(X_all_scaled)
df["PC1"], df["PC2"] = components[:, 0], components[:, 1]

loadings = pd.DataFrame(pca.components_.T, columns=["PC1", "PC2"], index=all_features)
print("PCA Loadings (Weights of original features in each PC):")
print(loadings)
print("\nExplained variance ratio:")
print(pca.explained_variance_ratio_)

# ----------------------------------------------------------------------
# 3. Clustering into design "phases"
#
#    Clustered on the DESIGN variables only (N_PV_hh, E_BESS_cap_kwh,
#    E_TESS_cap_kwh) -- cost/emissions are outputs of the design and
#    their scale would dominate the distance metric. A Gaussian Mixture
#    with diagonal covariance is used instead of KMeans, since the real
#    phases are elongated sweeps/ramps rather than round, equal-sized
#    blobs.
# ----------------------------------------------------------------------
X_design = StandardScaler().fit_transform(df[design_features])

n_phases = 2
gmm = GaussianMixture(
    n_components=n_phases, covariance_type="diag", random_state=42, n_init=10
)
df["cluster"] = gmm.fit_predict(X_design).astype(str)

print(f"\nUsing GaussianMixture(n_components={n_phases}, covariance_type='diag')")
print("Cluster means (physical units):")
print(df.groupby("cluster")[all_features].mean().round(2))
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

# ========================================================================
# FIGURE 1: pairwise design-variable comparisons (PV-BESS, PV-TESS, BESS-TESS)
# ========================================================================
fig1, axes1 = plt.subplots(1, 3, figsize=(18, 5.5))

sns.scatterplot(data=df, x="N_PV_hh", y="E_BESS_cap_kwh", ax=axes1[0], **scatter_kwargs)
axes1[0].set_title("PV Count vs Battery Storage Capacity")
axes1[0].set_xlabel("Number of PV panels (N_PV_hh)")
axes1[0].set_ylabel("Battery Storage Capacity (E_BESS_cap_kwh)")
axes1[0].grid(True, linestyle="--", alpha=0.6)

""" sns.scatterplot(data=df, x="N_PV_hh", y="E_TESS_cap_kwh", ax=axes1[1], **scatter_kwargs)
axes1[1].set_title("PV Count vs Thermal Storage Capacity")
axes1[1].set_xlabel("Number of PV panels (N_PV_hh)")
axes1[1].set_ylabel("Thermal Storage Capacity (E_TESS_cap_kwh)")
axes1[1].grid(True, linestyle="--", alpha=0.6)

sns.scatterplot(
    data=df, x="E_TESS_cap_kwh", y="E_BESS_cap_kwh", ax=axes1[2], **scatter_kwargs
)
axes1[2].set_title("Thermal vs Battery Storage Capacity")
axes1[2].set_xlabel("Thermal Storage Capacity (E_TESS_cap_kwh)")
axes1[2].set_ylabel("Battery Storage Capacity (E_BESS_cap_kwh)")
axes1[2].grid(True, linestyle="--", alpha=0.6) """

for ax in axes1:
    ax.legend(title="Phase (cluster)", loc="best", fontsize=8)

fig1.suptitle("Design variable comparisons, colored by phase", fontsize=14, y=1.02)
plt.tight_layout()
plt.savefig("design_variable_comparisons.png", dpi=150, bbox_inches="tight")

# ========================================================================
# FIGURE 2: PCA + Pareto frontier (colored by phase), plus the presence
# (interval) of each design component -- PV, BESS, TESS -- in each phase.
#
#    Bottom row shows, for each design variable (N_PV_hh, E_BESS_cap_kwh,
#    E_TESS_cap_kwh), a boxplot per phase: box = IQR, whiskers = min/max
#    range. This is "how present" that component is in each phase -- e.g.
#    a phase where E_TESS_cap_kwh sits tightly near 0 vs. one where it
#    sits tightly near 40 tells you TESS is "off" vs "on" in that phase.
# ========================================================================
from matplotlib.gridspec import GridSpec

fig2 = plt.figure(figsize=(18, 11))
gs = GridSpec(2, 6, figure=fig2)

ax_pca = fig2.add_subplot(gs[0, 0:3])
ax_pareto = fig2.add_subplot(gs[0, 3:6])
ax_pv = fig2.add_subplot(gs[1, 0:2])
ax_bess = fig2.add_subplot(gs[1, 2:4])
# ax_tess = fig2.add_subplot(gs[1, 4:6])

sns.scatterplot(data=df, x="PC1", y="PC2", ax=ax_pca, **scatter_kwargs)
ax_pca.set_title("PCA: First Two Principal Components, colored by phase")
ax_pca.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]*100:.1f}% variance)")
ax_pca.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]*100:.1f}% variance)")
ax_pca.grid(True, linestyle="--", alpha=0.6)
ax_pca.legend(title="Phase (cluster)", loc="best", fontsize=8)

sns.scatterplot(
    data=df,
    x="annual_cost_total_eur",
    y="annual_emissions_total_kg",
    ax=ax_pareto,
    **scatter_kwargs,
)
ax_pareto.set_title("Pareto Frontier, colored by phase")
ax_pareto.set_xlabel("Annual cost [EUR/year]")
ax_pareto.set_ylabel("Annual emissions [kg CO2eq/year]")
ax_pareto.grid(True, linestyle="--", alpha=0.6)
ax_pareto.legend(title="Phase (cluster)", loc="best", fontsize=8)

component_plot_specs = [
    (ax_pv, "N_PV_hh", "Number of PV panels (N_PV_hh)"),
    (ax_bess, "E_BESS_cap_kwh", "Battery Storage Capacity (E_BESS_cap_kwh)"),
    # (ax_tess, "E_TESS_cap_kwh", "Thermal Storage Capacity (E_TESS_cap_kwh)"),
]
for ax, col, ylabel in component_plot_specs:
    sns.boxplot(
        data=df,
        x="cluster",
        y=col,
        order=cluster_order,
        hue="cluster",
        hue_order=cluster_order,
        palette=color_map,
        legend=False,
        ax=ax,
    )
    ax.set_title(f"{col} interval per phase")
    ax.set_xlabel("Phase (cluster)")
    ax.set_ylabel(ylabel)
    ax.grid(True, linestyle="--", alpha=0.6)

fig2.suptitle(
    "Phase clustering: PCA, Pareto frontier, and component presence per phase",
    fontsize=14,
    y=1.02,
)
plt.tight_layout()
plt.savefig("pca_pareto_component_intervals.png", dpi=150, bbox_inches="tight")

plt.show()
