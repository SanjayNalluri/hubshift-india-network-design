import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

D = "data/processed"
cities = pd.read_csv(f"{D}/cities.csv")
sites  = pd.read_csv(f"{D}/sites.csv")
road   = pd.read_csv(f"{D}/road_km.csv", index_col=0)
P      = pd.read_csv("data/raw/parameters.csv").set_index("parameter")["value"]

FREIGHT    = P.FREIGHT_RS_TKM
MODULE_CAP = P.SQFT_SMALL * P.MARKET_SHARE * P.NATIONAL_T / P.DEPOT_SQFT
module_cost = dict(zip(sites.site, P.SQFT_SMALL * sites.rent * 12 * (1 + P.OPEX_RATIO) / 1e7))
demand = dict(zip(cities.city, cities.demand_t))

def network_cost(assign):
    """Annual fixed (modules) + freight cost, ₹ crore, for a city->site assignment."""
    a = assign.assign(d=assign.city.map(demand))
    a["km"] = [road.loc[s, c] for s, c in zip(a.site, a.city)]
    load = a.groupby("site").d.sum()
    fixed = sum(np.ceil(load[s] / MODULE_CAP) * module_cost[s] for s in load.index)
    freight = (a.d * a.km).sum() * FREIGHT / 1e7
    return fixed + freight, (a.d * a.km).sum() / a.d.sum()

def fail(assign, down):
    """DC `down` is shut. Its cities go to the nearest DC still open; extra space is rented there."""
    a = assign.copy()
    alive = [s for s in a.site.unique() if s != down]
    hit = a.site == down
    a.loc[hit, "site"] = [road.loc[alive, c].idxmin() for c in a.loc[hit, "city"]]
    return a, hit.sum()

networks = {"Pre-GST (18 DCs)": pd.read_csv("outputs/baseline_assignment.csv")[["city", "site"]]}
for oh in [0, 0.5, 2]:
    a = pd.read_csv(f"outputs/assign_oh_{oh:g}.csv")
    networks[f"Post-GST ₹{oh} cr ({a.site.nunique()} DCs)"] = a

rows = []
for name, a in networks.items():
    base_cost, base_km = network_cost(a)
    for dc in a.site.unique():
        a2, n_hit = fail(a, dc)
        c2, km2 = network_cost(a2)
        rows.append([name, dc, n_hit, base_cost, c2, (c2 / base_cost - 1) * 100, base_km, km2])

res = pd.DataFrame(rows, columns=["network", "failed_dc", "cities_rerouted", "cost_normal_cr",
                                  "cost_failed_cr", "cost_increase_%", "avg_km_normal", "avg_km_failed"])
res.round(2).to_csv("outputs/resilience_all_failures.csv", index=False)

summary = res.groupby("network", sort=False).agg(
    normal_cost_excl_overhead_cr=("cost_normal_cr", "first"),
    avg_increase_pct=("cost_increase_%", "mean"),
    worst_increase_pct=("cost_increase_%", "max"),
    worst_avg_km=("avg_km_failed", "max"))
summary["worst_dc"] = res.loc[res.groupby("network", sort=False)["cost_increase_%"].idxmax()].set_index("network")["failed_dc"]
print("SINGLE-DC FAILURE STRESS TEST\n")
print(summary.round(2).to_string())
summary.round(2).to_csv("outputs/resilience_summary.csv")

fig, ax = plt.subplots(figsize=(9, 4.5))
x = np.arange(len(summary))
ax.bar(x - 0.2, summary.avg_increase_pct, 0.4, label="Average DC failure")
ax.bar(x + 0.2, summary.worst_increase_pct, 0.4, label="Worst DC failure")
for i, r in enumerate(summary.itertuples()):
    ax.annotate(r.worst_dc, (i + 0.2, r.worst_increase_pct), ha="center", va="bottom", fontsize=7)
ax.set_xticks(x); ax.set_xticklabels(summary.index, fontsize=8)
ax.set_ylabel("Cost increase vs normal (%)"); ax.set_title("Resilience: cost impact of losing one DC")
ax.legend(); ax.grid(axis="y", alpha=0.3)
plt.tight_layout(); plt.savefig("outputs/05_resilience.png"); plt.close()
print("\nSaved resilience_all_failures.csv, resilience_summary.csv, 05_resilience.png")