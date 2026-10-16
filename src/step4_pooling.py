import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

cities = pd.read_csv("data/processed/cities.csv")
sweep  = pd.read_csv("outputs/milp_overhead_sweep.csv")
pre    = pd.read_csv("outputs/baseline_assignment.csv")[["city", "site"]]
mu     = dict(zip(cities.city, cities.demand_t))

def ss_index(assign):
    """Total safety stock, up to a constant (z * CV * sqrt(L)).
    Each DC: SS_j ∝ sqrt(sum of mu_i^2) over the cities it serves (independent demand, same CV)."""
    m2 = assign.city.map(mu) ** 2
    return m2.groupby(assign.site).sum().pow(0.5).sum()

pre_ss = ss_index(pre)
rows = [["Pre-GST (state-wise)", "-", pre["site"].nunique(), 0.0, 0.0]]
for oh in sweep.overhead_cr:
    a = pd.read_csv(f"outputs/assign_oh_{oh:g}.csv")
    saving = sweep.loc[sweep.overhead_cr == oh, "saving_%"].iloc[0]
    rows.append([f"Post-GST (overhead ₹{oh} cr)", oh, a.site.nunique(), saving, (ss_index(a) / pre_ss - 1) * 100])

single = np.sqrt(sum(v ** 2 for v in mu.values()))
rows.append(["Reference: 1 national DC", "-", 1, np.nan, (single / pre_ss - 1) * 100])
rows.append(["Reference: 1 DC per city", "-", len(mu), np.nan, (sum(mu.values()) / pre_ss - 1) * 100])

res = pd.DataFrame(rows, columns=["network", "overhead_cr", "DCs", "cost_saving_%", "safety_stock_vs_pre_%"])
print(res.round(1).to_string(index=False))
res.to_csv("outputs/pooling_results.csv", index=False)

post = res[res.network.str.startswith("Post")]
fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(post.DCs, post["safety_stock_vs_pre_%"], "o-", color="tab:red")
for r in post.itertuples():
    ax.annotate(f"₹{r.overhead_cr} cr", (r.DCs, r._5), textcoords="offset points", xytext=(5, 5), fontsize=8)
ax.axhline(0, color="grey", linestyle="--", label=f"Pre-GST level ({pre['site'].nunique()} DCs)")
ax.set_xlabel("Number of DCs in optimized network"); ax.set_ylabel("Safety stock vs pre-GST (%)")
ax.set_title("Risk pooling: fewer DCs → less safety stock"); ax.legend(); ax.grid(alpha=0.3)
plt.tight_layout(); plt.savefig("outputs/04_risk_pooling.png"); plt.close()
print("\nSaved pooling_results.csv and 04_risk_pooling.png")