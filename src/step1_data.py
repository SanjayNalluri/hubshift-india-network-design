import os, json, time
import numpy as np
import pandas as pd
import requests
import matplotlib.pyplot as plt

RAW, OUT = "data/raw", "data/processed"
os.makedirs(OUT, exist_ok=True); os.makedirs("outputs", exist_ok=True)

cities = pd.read_csv(f"{RAW}/cities_census2011.csv")
sites  = pd.read_csv(f"{RAW}/candidate_sites.csv")
kf     = pd.read_csv(f"{RAW}/kf_rent_clusters_2025.csv")
states = pd.read_csv(f"{RAW}/states.csv").set_index("state_code")["state_name"]
P      = pd.read_csv(f"{RAW}/parameters.csv").set_index("parameter")["value"]

print(f"Loaded {len(cities)} cities, {len(sites)} sites, {len(kf)} rent rows, {len(P)} parameters")

# Demand = population × kg per person × market share
cities["demand_t"] = (cities.population_2011 * P.KG_PER_CAPITA * P.MARKET_SHARE / 1000).round(0)

# Rent per market = median of Grade A cluster mid-points (Knight Frank 2025)
kf["gradeA_mid"] = (kf.gradeA_min + kf.gradeA_max) / 2
market_rent = kf.dropna(subset=["gradeA_mid"]).groupby("market")["gradeA_mid"].median()
sites["rent"] = sites["rent_market"].map(market_rent)

# Capacity and annual fixed cost for each warehouse size
throughput = P.MARKET_SHARE * P.NATIONAL_T / P.DEPOT_SQFT      # t per sq ft per year
for size in ["SMALL", "LARGE"]:
    area = P[f"SQFT_{size}"]
    sites[f"cap_{size.lower()}_t"]    = round(area * throughput)
    sites[f"fixed_{size.lower()}_cr"] = (area * sites.rent * 12 * (1 + P.OPEX_RATIO) / 1e7).round(3)

print(f"Throughput: {throughput:.2f} t/sqft/yr | Total demand: {cities.demand_t.sum():,.0f} t/yr")

CACHE = f"{OUT}/geocode_cache.json"
cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}

def geocode(name, state_code):
    q = f"{name}, {states[state_code]}, India"
    if q not in cache:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": q, "format": "json", "limit": 1, "countrycodes": "in"},
                         headers={"User-Agent": "HubShift-India-student-project"}, timeout=30)
        r.raise_for_status(); res = r.json(); time.sleep(1.1)
        if not res: raise ValueError(f"Not found: {q}")
        cache[q] = {"lat": float(res[0]["lat"]), "lon": float(res[0]["lon"]), "found": res[0]["display_name"]}
        json.dump(cache, open(CACHE, "w"), indent=1)
    g = cache[q]
    return g["lat"], g["lon"], states[state_code].lower() in g["found"].lower()

for df in (cities, sites):
    df["lat"], df["lon"], df["state_ok"] = zip(*[geocode(r.geocode_name, r.state_code) for r in df.itertuples()])

bad = pd.concat([cities.loc[~cities.state_ok, ["city", "state_code"]],
                 sites.loc[~sites.state_ok, ["site", "state_code"]]])
print("Geocoding state mismatches:", "none ✅" if bad.empty else f"\n{bad}")

def haversine(la1, lo1, la2, lo2):
    p1, p2 = np.radians(la1), np.radians(la2)
    a = np.sin((p2-p1)/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(np.radians(lo2-lo1)/2)**2
    return 2 * 6371 * np.arcsin(np.sqrt(a))

pts = pd.concat([sites[["lon", "lat"]], cities[["lon", "lat"]]]).values
ns, nc = len(sites), len(cities)
url = "https://router.project-osrm.org/table/v1/driving/" + ";".join(f"{lo:.5f},{la:.5f}" for lo, la in pts)
r = requests.get(url, params={"sources": ";".join(map(str, range(ns))),
                              "destinations": ";".join(map(str, range(ns, ns + nc))),
                              "annotations": "distance"}, timeout=120)
r.raise_for_status(); res = r.json(); assert res["code"] == "Ok", res

road = pd.DataFrame(np.array(res["distances"], dtype=float) / 1000,
                    index=sites.site, columns=cities.city).round(1)
straight = pd.DataFrame([[haversine(s.lat, s.lon, c.lat, c.lon) for c in cities.itertuples()]
                         for s in sites.itertuples()], index=sites.site, columns=cities.city)
ratio = (road / straight)[straight > 50]
print(f"Road/straight ratio: median {np.nanmedian(ratio):.2f}, min {np.nanmin(ratio):.2f}, max {np.nanmax(ratio):.2f}")
print("Missing routes:", int(road.isna().sum().sum()), "| Delhi -> Mumbai:", f"{road.loc['Delhi', 'Mumbai']:.0f} km")

cities.to_csv(f"{OUT}/cities.csv", index=False)
sites.to_csv(f"{OUT}/sites.csv", index=False)
road.to_csv(f"{OUT}/road_km.csv")

print("\n", sites[["site", "rent", "rent_type", "fixed_small_cr", "fixed_large_cr"]].to_string(index=False))

plt.figure(figsize=(8, 9))
plt.scatter(cities.lon, cities.lat, s=cities.demand_t / 300, alpha=0.4, label="Cities (size = demand)")
for typ, col in [("verified", "green"), ("proxy", "orange")]:
    s = sites[sites.rent_type == typ]
    plt.scatter(s.lon, s.lat, marker="^", s=90, c=col, label=f"Sites: {typ} rent")
for c in cities[cities.population_2011 > 4e6].itertuples():
    plt.annotate(c.city, (c.lon, c.lat), fontsize=8)
plt.title("HubShift India: 52 million-plus cities and 27 candidate sites")
plt.xlabel("Longitude"); plt.ylabel("Latitude"); plt.legend(loc="lower left")
plt.tight_layout(); plt.savefig("outputs/01_network_inputs.png"); plt.close()
print("\nSaved data/processed/*.csv and outputs/01_network_inputs.png")

