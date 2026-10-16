import numpy as np
import pandas as pd
import pulp
import matplotlib.pyplot as plt

D = "data/processed"
cities = pd.read_csv(f"{D}/cities.csv")
sites  = pd.read_csv(f"{D}/sites.csv")
road   = pd.read_csv(f"{D}/road_km.csv", index_col=0)
P      = pd.read_csv("data/raw/parameters.csv").set_index("parameter")["value"]
base   = pd.read_csv("outputs/baseline_warehouses.csv")

FREIGHT    = P.FREIGHT_RS_TKM
MODULE_CAP = P.SQFT_SMALL * P.MARKET_SHARE * P.NATIONAL_T / P.DEPOT_SQFT
module_cost = dict(zip(sites.site, P.SQFT_SMALL * sites.rent * 12 * (1 + P.OPEX_RATIO) / 1e7))

I = list(cities.city)                                   # demand cities
J = list(sites.site)                                    # candidate sites
d = dict(zip(cities.city, cities.demand_t))             # demand, t/yr
cost = {(j, i): d[i] * road.loc[j, i] * FREIGHT / 1e7 for j in J for i in I}   # ₹ cr/yr if j serves i
MAX_MODULES = int(np.ceil(sum(d.values()) / MODULE_CAP))

def solve(overhead_cr):
    m = pulp.LpProblem("HubShift_CFLP", pulp.LpMinimize)
    x = {(j, i): pulp.LpVariable(f"x_{a}_{b}", cat="Binary") for a, j in enumerate(J) for b, i in enumerate(I)}
    y = {j: pulp.LpVariable(f"y_{a}", cat="Binary") for a, j in enumerate(J)}
    n = {j: pulp.LpVariable(f"n_{a}", lowBound=0, cat="Integer") for a, j in enumerate(J)}

    m += (pulp.lpSum(module_cost[j] * n[j] + overhead_cr * y[j] for j in J)
          + pulp.lpSum(cost[j, i] * x[j, i] for j in J for i in I))
    for i in I:
        m += pulp.lpSum(x[j, i] for j in J) == 1                        # every city served by exactly one DC
    for j in J:
        m += pulp.lpSum(d[i] * x[j, i] for i in I) <= MODULE_CAP * n[j]  # capacity = modules built
        m += n[j] <= MAX_MODULES * y[j]                                  # modules only at open sites
        for i in I:
            m += x[j, i] <= y[j]                                         # only open sites can serve

    m.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=120))
    assign = pd.DataFrame([(i, j) for (j, i), v in x.items() if v.value() > 0.5], columns=["city", "site"])
    opened = pd.DataFrame([(j, int(round(n[j].value()))) for j in J if n[j].value() > 0.5], columns=["site", "modules"])
    fixed = sum(module_cost[j] * n[j].value() for j in J)
    transport = sum(cost[j, i] * x[j, i].value() for j in J for i in I)
    return dict(status=pulp.LpStatus[m.status], fixed=fixed, transport=transport,
                overhead=overhead_cr * len(opened), assign=assign, opened=opened)

OVERHEADS = [0, 0.25, 0.5, 1.0, 2.0]     # ₹ crore per site per year (not publicly sourced -> swept)
n_base = len(base)
rows, runs = [], {}
for oh in OVERHEADS:
    r = solve(oh); runs[oh] = r
    post = r["fixed"] + r["transport"] + r["overhead"]
    pre  = base.fixed_cr.sum() + base.transport_cr.sum() + oh * n_base
    rows.append([oh, r["status"], n_base, len(r["opened"]), pre, post, (1 - post / pre) * 100,
                 r["fixed"], r["transport"], r["overhead"]])

res = pd.DataFrame(rows, columns=["overhead_cr", "status", "DCs_pre", "DCs_post", "cost_pre_cr",
                                  "cost_post_cr", "saving_%", "fixed_cr", "transport_cr", "overhead_total_cr"])
print("\nPRE-GST vs POST-GST (₹ crore/yr), across per-site overhead levels:\n")
print(res.round(2).to_string(index=False))

always = set.intersection(*[set(r["opened"].site) for r in runs.values()])
print(f"\nSites opened in EVERY scenario ({len(always)}): {sorted(always)}")
res.to_csv("outputs/milp_overhead_sweep.csv", index=False)

# ---- Chart 1: cost and DC count vs overhead
fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
ax[0].plot(res.overhead_cr, res.cost_pre_cr, "o-", label="Pre-GST (state-wise)")
ax[0].plot(res.overhead_cr, res.cost_post_cr, "o-", label="Post-GST (optimized)")
ax[0].set_xlabel("Overhead per site (₹ cr/yr)"); ax[0].set_ylabel("Total cost (₹ cr/yr)")
ax[0].set_title("Total network cost"); ax[0].legend(); ax[0].grid(alpha=0.3)
ax[1].plot(res.overhead_cr, res.DCs_pre, "o-", label="Pre-GST")
ax[1].plot(res.overhead_cr, res.DCs_post, "o-", label="Post-GST")
ax[1].set_xlabel("Overhead per site (₹ cr/yr)"); ax[1].set_ylabel("Number of warehouses")
ax[1].set_title("Network size"); ax[1].legend(); ax[1].grid(alpha=0.3)
plt.tight_layout(); plt.savefig("outputs/02_overhead_sweep.png"); plt.close()

# ---- Chart 2: map of the optimized network (illustrative overhead)
OH_SHOW = 0.5
r = runs[OH_SHOW]
a = r["assign"].merge(cities[["city", "lat", "lon", "demand_t"]], on="city") \
               .merge(sites[["site", "lat", "lon"]], on="site", suffixes=("", "_dc"))
plt.figure(figsize=(8, 9))
for row in a.itertuples():
    plt.plot([row.lon_dc, row.lon], [row.lat_dc, row.lat], color="grey", linewidth=0.6, alpha=0.6)
plt.scatter(cities.lon, cities.lat, s=cities.demand_t / 300, alpha=0.4, label="Cities (size = demand)")
op = r["opened"].merge(sites[["site", "lat", "lon"]], on="site")
plt.scatter(op.lon, op.lat, marker="^", s=40 + op.modules * 40, c="red", label="Open DCs (size = modules)")
for row in op.itertuples():
    plt.annotate(row.site, (row.lon, row.lat), fontsize=7)
plt.title(f"Post-GST optimized network ({len(op)} DCs, overhead ₹{OH_SHOW} cr/site)")
plt.xlabel("Longitude"); plt.ylabel("Latitude"); plt.legend(loc="lower left")
plt.tight_layout(); plt.savefig("outputs/03_optimized_network.png"); plt.close()

r["assign"].to_csv("outputs/postgst_assignment.csv", index=False)
r["opened"].to_csv("outputs/postgst_warehouses.csv", index=False)
print("\nSaved milp_overhead_sweep.csv, postgst_*.csv, 02_overhead_sweep.png, 03_optimized_network.png")

for oh, r in runs.items():
    r["assign"].to_csv(f"outputs/assign_oh_{oh:g}.csv", index=False)