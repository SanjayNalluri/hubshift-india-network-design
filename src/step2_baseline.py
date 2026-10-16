import math
import numpy as np
import pandas as pd

D = "data/processed"
cities = pd.read_csv(f"{D}/cities.csv")
sites  = pd.read_csv(f"{D}/sites.csv")
road   = pd.read_csv(f"{D}/road_km.csv", index_col=0)
P      = pd.read_csv("data/raw/parameters.csv").set_index("parameter")["value"]

FREIGHT     = P.FREIGHT_RS_TKM                                   # ₹ per tonne-km
THROUGHPUT  = P.MARKET_SHARE * P.NATIONAL_T / P.DEPOT_SQFT       # t per sq ft per yr
MODULE_SQFT = P.SQFT_SMALL                                       # 20,000 sq ft per module
MODULE_CAP  = MODULE_SQFT * THROUGHPUT                           # t/yr per module
sites["module_cost_cr"] = MODULE_SQFT * sites.rent * 12 * (1 + P.OPEX_RATIO) / 1e7
print(f"Module: {MODULE_SQFT:,.0f} sq ft = {MODULE_CAP:,.0f} t/yr | Freight ₹{FREIGHT}/t-km")

state_wh = sites[sites.state_wh].set_index("state_code")["site"]
cities["site"] = cities.state_code.map(state_wh)
cities["km"]   = [road.loc[s, c] for s, c in zip(cities.site, cities.city)]
cities["transport_cr"] = cities.demand_t * cities.km * FREIGHT / 1e7

nearest_site = road.idxmin()
cities["nearest_site"] = cities.city.map(nearest_site)
cities["nearest_km"]   = [road.loc[s, c] for s, c in zip(cities.nearest_site, cities.city)]

wh = cities.groupby("site").agg(demand_t=("demand_t", "sum"), cities=("city", "count"),
                                transport_cr=("transport_cr", "sum")).reset_index()
wh = wh.merge(sites[["site", "module_cost_cr", "rent_type"]], on="site")
wh["modules"]  = np.ceil(wh.demand_t / MODULE_CAP).astype(int)
wh["sqft"]     = wh.modules * MODULE_SQFT
wh["fixed_cr"] = wh.modules * wh.module_cost_cr
wh["util_%"]   = (wh.demand_t / (wh.modules * MODULE_CAP) * 100).round(1)

fixed, transport = wh.fixed_cr.sum(), wh.transport_cr.sum()
avg_km = (cities.demand_t * cities.km).sum() / cities.demand_t.sum()
print(f"\nPRE-GST BASELINE: {len(wh)} warehouses, {wh.sqft.sum():,.0f} sq ft")
print(f"  Fixed (rent + ops): ₹{fixed:.2f} cr | Transport: ₹{transport:.2f} cr | TOTAL: ₹{fixed + transport:.2f} cr/yr")
print(f"  Demand-weighted avg distance: {avg_km:.0f} km")
print("\n", wh.sort_values("demand_t", ascending=False).round(2).to_string(index=False))

cities["nearest_state"] = cities.nearest_site.map(sites.set_index("site").state_code)
cities["extra_km"] = cities.km - cities.nearest_km
cities["reason"] = np.where(cities.extra_km <= 0, "-",
                   np.where(cities.nearest_state != cities.state_code, "State border", "One warehouse per state"))
cities["extra_cr"] = cities.demand_t * cities.extra_km * FREIGHT / 1e7

for reason in ["State border", "One warehouse per state"]:
    sub = cities[cities.reason == reason].sort_values("extra_km", ascending=False)
    print(f"\n{reason.upper()}: {len(sub)} cities, extra freight ₹{sub.extra_cr.sum():.2f} cr/yr")
    print(sub[["city", "state_code", "site", "km", "nearest_site", "nearest_km", "extra_km"]]
          .round(0).to_string(index=False))

cities.to_csv("outputs/baseline_assignment.csv", index=False)
wh.to_csv("outputs/baseline_warehouses.csv", index=False)

