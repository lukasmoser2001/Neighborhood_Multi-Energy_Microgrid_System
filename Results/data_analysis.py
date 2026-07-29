import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

# 1. Load the data
df = pd.read_csv(
    "Results/Optimization_2026-07-29_17-41-05/nsga2_D_grid_ashp_pv_bess_tess/pareto_solutions.csv"
)

# 2. Setup the figure for the plot
fig, axes = plt.subplots(1, 2, figsize=(15, 6))

# --- Comparative Plot ---
sns.scatterplot(
    data=df,
    x="E_TESS_cap_kwh",
    y="E_BESS_cap_kwh",
    ax=axes[0],
    color="blue",
    alpha=0.7,
)
axes[0].set_title("Comparative Plot: E_BESS_cap_kwh vs E_TESS_cap_kwh")
axes[0].set_xlabel("Thermal Storage Capacity (E_TESS_cap_kwh)")
axes[0].set_ylabel("Battery Storage Capacity (E_BESS_cap_kwh)")
axes[0].grid(True, linestyle="--", alpha=0.6)

# --- PCA Preparation & Execution ---
# We use all numerical columns for the PCA to understand the overall variance
features = [
    "N_PV_hh",
    "E_BESS_cap_kwh",
    "E_TESS_cap_kwh",
    "annual_cost_total_eur",
    "annual_emissions_total_kg",
]
X = df[features]

# Standardize the features before applying PCA
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# Initialize and fit PCA for 2 components
pca = PCA(n_components=2)
components = pca.fit_transform(X_scaled)

# Add principal components back to the dataframe for plotting
df["PC1"] = components[:, 0]
df["PC2"] = components[:, 1]

# --- PCA Plot ---
sns.scatterplot(data=df, x="PC1", y="PC2", ax=axes[1], color="coral", alpha=0.7)
axes[1].set_title("PCA: First Two Principal Components")
axes[1].set_xlabel(
    f"Principal Component 1 ({pca.explained_variance_ratio_[0]*100:.1f}% variance)"
)
axes[1].set_ylabel(
    f"Principal Component 2 ({pca.explained_variance_ratio_[1]*100:.1f}% variance)"
)
axes[1].grid(True, linestyle="--", alpha=0.6)

plt.tight_layout()
plt.show()

# 3. Explain the directions (extract and print loadings)
loadings = pd.DataFrame(pca.components_.T, columns=["PC1", "PC2"], index=features)

print("PCA Loadings (Weights of original features in each PC):")
print(loadings)
print("\nExplained variance ratio:")
print(pca.explained_variance_ratio_)
