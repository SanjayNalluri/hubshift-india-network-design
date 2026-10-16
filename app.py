"""HubShift India: post-GST distribution network redesign (Streamlit app)."""
import numpy as np
import pandas as pd
import pulp
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="HubShift India", page_icon="🛣️", layout="wide",
                   initial_sidebar_state="collapsed")

# ------------------------------------------------------------------ style
# Palette: vintage Indian railway map / poster
NAVY, TEAL, GOLD, MAROON, IVORY, SAND, INK, GREY, LINE = (
    "#14213D", "#0F5C4C", "#E9A23B", "#8C2F39", "#F8F5EE", "#EFE4CC", "#1B2433", "#5F6672", "#DDD5C3")
GREEN, YELLOW, RED = TEAL, GOLD, MAROON          # names used further down

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Overpass:wght@400;600;800&display=swap');
.stApp, .stApp p, .stApp li, .stApp label, .stApp td, .stApp th, .stApp input {{ font-family: 'Overpass', sans-serif; }}
.stApp {{ background: {IVORY}; }}
.block-container {{ padding-top: 3.2rem; max-width: 1180px; }}

/* top bar */
header[data-testid="stHeader"] {{ background: {NAVY}; border-bottom: 4px solid {GOLD}; }}
header[data-testid="stHeader"] a, header[data-testid="stHeader"] span, header[data-testid="stHeader"] p,
header[data-testid="stHeader"] button {{ color: #F3EEE2 !important; font-family: 'Overpass', sans-serif; font-weight: 600; }}
header[data-testid="stHeader"] a[aria-current="page"], header[data-testid="stHeader"] a:hover {{ background: rgba(233,162,59,.22) !important; }}

/* page title band */
.hero {{ background: {NAVY}; color: #F3EEE2; margin: -0.7rem calc(50% - 50vw) 1.6rem; padding: 2.6rem calc(50vw - 50% + 1rem) 2.2rem;
         border-bottom: 6px solid {GOLD}; }}
.hero h1 {{ color: #FFFFFF; font-weight: 800; font-size: 2.6rem; line-height: 1.12; max-width: 24ch; margin: 0 0 .7rem; letter-spacing: -0.01em; }}
.hero p {{ color: #D9D3C3; font-size: 1.18rem; line-height: 1.55; max-width: 62ch; margin: 0; }}
.hero .stones {{ margin-top: 1.6rem; }}
.hero .stone-note {{ color: #D9D3C3; }}

h2, h3 {{ font-family: 'Overpass', sans-serif; color: {NAVY}; letter-spacing: -0.01em; }}
h2 {{ font-weight: 800; font-size: 1.55rem; margin-top: 1.8rem; padding-bottom: .3rem; border-bottom: 3px solid {GOLD}; display: inline-block; }}
h3 {{ font-weight: 700; font-size: 1.15rem; color: {MAROON}; }}
p, li {{ font-size: 1.02rem; line-height: 1.6; max-width: 70ch; color: {INK}; }}
.muted {{ color: {GREY}; font-size: 0.93rem; }}

/* NH milestone stones */
.stones {{ display: flex; gap: 2rem; align-items: flex-end; flex-wrap: wrap; }}
.stone {{ width: 128px; text-align: center; border: 2px solid #0B1426; border-radius: 64px 64px 6px 6px;
          overflow: hidden; background: #FFFFFF; box-shadow: 0 6px 0 #0B1426; }}
.stone .cap {{ background: {GOLD}; padding: 20px 6px 8px; font-weight: 800; font-size: 0.95rem; color: {NAVY}; }}
.stone .km {{ padding: 10px 4px 4px; font-weight: 800; font-size: 2.3rem; color: {NAVY}; line-height: 1; }}
.stone .unit {{ padding-bottom: 12px; font-size: 0.85rem; color: {GREY}; }}
.stone.old .km {{ color: {MAROON}; }}
.stone.new .km {{ color: {TEAL}; }}
.stone-note {{ font-size: 0.92rem; max-width: 20ch; padding-bottom: 8px; }}

/* readout strip */
.readout {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); background: #FFFFFF;
            border: 1px solid {LINE}; border-top: 5px solid {TEAL}; margin: 0.4rem 0 1.4rem; }}
.readout div {{ padding: 0.9rem 1.1rem 1rem; border-right: 1px solid {LINE}; }}
.readout div:last-child {{ border-right: none; }}
.readout b {{ display: block; font-size: 1.75rem; font-weight: 800; color: {NAVY}; line-height: 1.15; }}
.readout span {{ font-size: 0.9rem; color: {GREY}; }}
.good {{ color: {TEAL} !important; }} .bad {{ color: {MAROON} !important; }}

/* tables */
table.cmp {{ border-collapse: collapse; width: 100%; font-size: 0.98rem; border: 1px solid {LINE}; background: #FFFFFF; }}
table.cmp th, table.cmp td {{ border-left: none !important; border-right: none !important; border-top: none; }}
table.cmp th {{ text-align: left; font-weight: 600; color: #F3EEE2; background: {NAVY}; padding: 10px 12px; }}
table.cmp td {{ border-bottom: 1px solid {LINE}; padding: 10px 12px; color: {INK}; }}
table.cmp tr:nth-child(even) td {{ background: #FBF9F4; }}
table.cmp tr.pick td {{ background: #FBE9C6; font-weight: 700; border-left: 0; }}
table.cmp td.num {{ font-variant-numeric: tabular-nums; }}
a {{ color: {TEAL}; }}
[data-testid="stDataFrame"] {{ border: 1px solid {LINE}; }}
[data-testid="stPlotlyChart"] {{ background: #FFFFFF; border: 1px solid {LINE}; padding: 6px; }}
@media (max-width: 640px) {{ .hero h1 {{ font-size: 2rem; }} .stone {{ width: 108px; }} }}
</style>
""", unsafe_allow_html=True)


def hero(title, lede, extra=""):
    st.markdown(f"<div class='hero'><h1>{title}</h1><p>{lede}</p>{extra}</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ data
@st.cache_data
def load():
    D = "data/processed"
    cities = pd.read_csv(f"{D}/cities.csv")
    sites = pd.read_csv(f"{D}/sites.csv")
    road = pd.read_csv(f"{D}/road_km.csv", index_col=0)
    P = pd.read_csv("data/raw/parameters.csv").set_index("parameter")["value"]
    base = pd.read_csv("outputs/baseline_warehouses.csv")
    pre = pd.read_csv("outputs/baseline_assignment.csv")[["city", "site"]]
    return cities, sites, road, P, base, pre

cities, sites, road, P, base, pre = load()
MODULE_CAP = P.SQFT_SMALL * P.MARKET_SHARE * P.NATIONAL_T / P.DEPOT_SQFT
module_cost = dict(zip(sites.site, P.SQFT_SMALL * sites.rent * 12 * (1 + P.OPEX_RATIO) / 1e7))
demand = dict(zip(cities.city, cities.demand_t))


@st.cache_data(show_spinner=False)
def solve(overhead, freight, closed=()):
    """Capacitated facility location MILP. Returns assignment, open sites, fixed and freight cost."""
    I, J = list(cities.city), [j for j in sites.site if j not in closed]
    cost = {(j, i): demand[i] * road.loc[j, i] * freight / 1e7 for j in J for i in I}
    M = int(np.ceil(sum(demand.values()) / MODULE_CAP))
    m = pulp.LpProblem("HubShift", pulp.LpMinimize)
    x = {(j, i): pulp.LpVariable(f"x_{a}_{b}", cat="Binary") for a, j in enumerate(J) for b, i in enumerate(I)}
    y = {j: pulp.LpVariable(f"y_{a}", cat="Binary") for a, j in enumerate(J)}
    n = {j: pulp.LpVariable(f"n_{a}", lowBound=0, cat="Integer") for a, j in enumerate(J)}
    m += pulp.lpSum(module_cost[j] * n[j] + overhead * y[j] for j in J) + pulp.lpSum(cost[k] * x[k] for k in x)
    for i in I:
        m += pulp.lpSum(x[j, i] for j in J) == 1
    for j in J:
        m += pulp.lpSum(demand[i] * x[j, i] for i in I) <= MODULE_CAP * n[j]
        m += n[j] <= M * y[j]
        for i in I:
            m += x[j, i] <= y[j]
    m.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=60))
    assign = pd.DataFrame([(i, j) for (j, i), v in x.items() if v.value() > 0.5], columns=["city", "site"])
    opened = pd.DataFrame([(j, int(round(n[j].value()))) for j in J if n[j].value() > 0.5],
                          columns=["site", "modules"])
    fixed = sum(module_cost[j] * n[j].value() for j in J)
    freight_cost = sum(cost[k] * x[k].value() for k in x)
    return assign, opened, fixed, freight_cost


def evaluate(assign, freight):
    """Fixed (modules) + freight cost and avg km for any assignment."""
    a = assign.assign(d=assign.city.map(demand))
    a["km"] = [road.loc[s, c] for s, c in zip(a.site, a.city)]
    load_ = a.groupby("site").d.sum()
    fixed = sum(np.ceil(load_[s] / MODULE_CAP) * module_cost[s] for s in load_.index)
    return fixed, (a.d * a.km).sum() * freight / 1e7, (a.d * a.km).sum() / a.d.sum(), a


def ss_index(assign):
    return (assign.city.map(demand) ** 2).groupby(assign.site).sum().pow(0.5).sum()


def pre_total(overhead, freight):
    f, t, _, _ = evaluate(pre, freight)
    return f + t + overhead * pre.site.nunique()


def network_map(assign, closed=(), height=560, title=None):
    a = assign.merge(cities[["city", "lat", "lon", "demand_t"]], on="city") \
              .merge(sites[["site", "lat", "lon", "rent", "rent_type"]], on="site", suffixes=("", "_dc"))
    lon, lat = [], []
    for r in a.itertuples():
        lon += [r.lon_dc, r.lon, None]; lat += [r.lat_dc, r.lat, None]
    fig = go.Figure()
    fig.add_trace(go.Scattergeo(lon=lon, lat=lat, mode="lines", line=dict(width=1.2, color="rgba(15,92,76,0.55)"),
                                hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scattergeo(lon=cities.lon, lat=cities.lat, mode="markers", name="City",
                                marker=dict(size=np.sqrt(cities.demand_t) / 22 + 3, color=NAVY, opacity=0.75),
                                text=[f"<b>{c}</b><br>{d:,.0f} t a year" for c, d in zip(cities.city, cities.demand_t)],
                                hoverinfo="text"))
    dc = a.groupby(["site", "lat_dc", "lon_dc", "rent", "rent_type"]).agg(n=("city", "count"), t=("demand_t", "sum")).reset_index()
    fig.add_trace(go.Scattergeo(lon=dc.lon_dc, lat=dc.lat_dc, mode="markers", name="Warehouse",
                                marker=dict(size=13, color=MAROON, symbol="square", line=dict(width=2, color=GOLD)),
                                text=[f"<b>{s}</b><br>serves {n} cities, {t:,.0f} t a year<br>rent ₹{r}/sq ft ({'Knight Frank' if k == 'verified' else 'proxy'})"
                                      for s, n, t, r, k in zip(dc.site, dc.n, dc.t, dc.rent, dc.rent_type)],
                                hoverinfo="text"))
    if closed:
        cs = sites[sites.site.isin(closed)]
        fig.add_trace(go.Scattergeo(lon=cs.lon, lat=cs.lat, mode="markers", name="Shut down",
                                    marker=dict(size=15, color="#000000", symbol="x"), text=cs.site, hoverinfo="text"))
    fig.update_geos(lonaxis_range=[67.5, 93.5], lataxis_range=[7, 36], showcountries=True,
                    countrycolor="#A8957A", showland=True, landcolor=SAND, showocean=True, oceancolor="#D7E5EC",
                    showcoastlines=True, coastlinecolor="#A8957A", bgcolor="#D7E5EC", showframe=False, resolution=50,
                    projection_type="mercator")
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=30 if title else 0, b=0),
                      title=dict(text=title, font=dict(family="Overpass", size=16, color=NAVY), x=0) if title else None,
                      legend=dict(orientation="h", y=-0.02, x=0, font=dict(family="Overpass", color=INK)),
                      paper_bgcolor="white", font=dict(family="Overpass"))
    return fig


def readout(items):
    cells = "".join(f"<div><b class='{cls}'>{val}</b><span>{label}</span></div>" for val, label, cls in items)
    st.markdown(f"<div class='readout'>{cells}</div>", unsafe_allow_html=True)


FREIGHT0 = float(P.FREIGHT_RS_TKM)

# ------------------------------------------------------------------ pages
def page_finding():
    hero("GST let an edible-oil distributor cut logistics cost by about a quarter",
         "Most of the saving comes from ignoring state borders and putting warehouses where people live, "
         "not from running fewer of them.",
         "<div class='stones'>"
         "<div class='stone old'><div class='cap'>Lucknow</div><div class='km'>469</div><div class='unit'>km</div></div>"
         "<div class='stone new'><div class='cap'>Delhi</div><div class='km'>56</div><div class='unit'>km</div></div>"
         "<div class='stone-note'>Distance from Ghaziabad to its warehouse, before and after GST.</div></div>")
    st.markdown("<p class='muted'>Ghaziabad is in Uttar Pradesh, so before GST its stock came from the state warehouse in Lucknow. "
                "Delhi's warehouse is next door.</p>", unsafe_allow_html=True)

    post_assign, post_open, f, t = solve(0.5, FREIGHT0)
    readout([
        ("₹14.6 cr", "a year lost to the old state-wise layout", ""),
        ("−22.9%", "annual cost with the redesigned network", "good"),
        ("17", "warehouses, down from 18", ""),
        ("Nagpur", "picked as a hub in every scenario", ""),
    ])

    st.markdown("## Before and after")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(network_map(pre, height=470, title="Before GST: one warehouse per state"),
                        width="stretch", config={"displayModeBar": False})
    with c2:
        st.plotly_chart(network_map(post_assign, height=470, title="After GST: 17 warehouses, no borders"),
                        width="stretch", config={"displayModeBar": False})

    st.markdown("## There is no single best network")
    st.markdown("The right answer depends on what it costs to run each site (a manager, security, IT). "
                "That number isn't published anywhere, so the model was solved across the whole range.")
    st.markdown(f"""
<table class='cmp'>
<tr><th>Network</th><th>Warehouses</th><th>Cost vs before GST</th><th>Safety stock vs before</th><th>If the worst site shuts</th></tr>
<tr><td>Spread out, cheap sites</td><td class='num'>21</td><td class='num'>−27.5%</td><td class='num'>+9.6%</td><td class='num'>+25% cost</td></tr>
<tr class='pick'><td>Balanced</td><td class='num'>17</td><td class='num'>−22.9%</td><td class='num'>+4.7%</td><td class='num'>+24% cost</td></tr>
<tr><td>Consolidated, costly sites</td><td class='num'>11</td><td class='num'>−23.3%</td><td class='num'>−10.6%</td><td class='num bad'>+59% cost</td></tr>
</table>""", unsafe_allow_html=True)
    st.markdown("<p class='muted'>Fewer warehouses pool inventory, but losing one hurts far more. "
                "In the 11-site network, Kolkata also serves all of Jharkhand, so losing it costs 59% more.</p>", unsafe_allow_html=True)
    st.markdown("Try your own numbers on **Design a network**, or shut a warehouse down on **Stress test**.")


def page_design():
    hero("Design a network", "Set the two costs the model is most sensitive to. "
         "It re-solves the full optimization each time, in about a second.")

    c1, c2, c3 = st.columns([1, 1, 1.2])
    with c1:
        overhead = st.slider("Running cost per warehouse (₹ crore a year)", 0.0, 2.0, 0.5, 0.05,
                             help="Manager, security, IT and other costs that don't depend on size. No public figure exists.")
    with c2:
        freight = st.slider("Trucking rate (₹ per tonne-km)", 1.5, 8.0, FREIGHT0, 0.1,
                            help="₹5.0 is the market rate for a 32 ft, 16–18 t truck. ₹1.51 is the DPIIT figure for heavy bulk trailers.")
    with c3:
        closed = st.multiselect("Sites you can't use", list(sites.site),
                                help="Leave out sites you don't want the model to consider.")

    with st.spinner("Optimizing…"):
        assign, opened, fixed, freight_cost = solve(overhead, freight, tuple(closed))
    total = fixed + freight_cost + overhead * len(opened)
    before = pre_total(overhead, freight)
    _, _, avg_km, a = evaluate(assign, freight)
    ss = (ss_index(assign) / ss_index(pre) - 1) * 100
    saving = (total / before - 1) * 100

    readout([
        (f"₹{total:.1f} cr", "total cost a year", ""),
        (f"{saving:+.1f}%".replace("-", "−"), f"vs ₹{before:.1f} cr before GST", "good" if saving < 0 else "bad"),
        (f"{len(opened)}", "warehouses open", ""),
        (f"{avg_km:.0f} km", "average trip to a city", ""),
        (f"{ss:+.1f}%".replace("-", "−"), "safety stock vs before GST", "good" if ss < 0 else ""),
    ])

    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(network_map(assign, closed), width="stretch", config={"displayModeBar": False})
    with right:
        st.markdown("### Where the money goes")
        f0, t0, _, _ = evaluate(pre, freight)
        st.dataframe(pd.DataFrame({"Before GST": [f0, t0, overhead * pre.site.nunique(), before],
                                   "Redesigned": [fixed, freight_cost, overhead * len(opened), total]},
                                  index=["Warehouse space", "Trucking", "Running cost", "Total"]).round(1),
                     width="stretch")
        st.markdown("### Warehouses")
        tbl = a.groupby("site").agg(Cities=("city", "count"), Tonnes=("d", "sum")).reset_index() \
               .merge(opened, on="site").rename(columns={"site": "Site", "modules": "Size (×20k sq ft)"})
        st.dataframe(tbl.sort_values("Tonnes", ascending=False), hide_index=True, width="stretch", height=330,
                     column_config={"Tonnes": st.column_config.NumberColumn(format="%d")})


def page_stress():
    hero("Stress test", "Shut one warehouse and send its cities to the nearest one still open, "
         "as a company would in a flood or strike. No re-planning, just rerouting.")

    options = {"Before GST (18 sites)": ("pre", None), "Spread out (21 sites)": ("post", 0.0),
               "Balanced (17 sites)": ("post", 0.5), "Consolidated (11 sites)": ("post", 2.0)}
    c1, c2 = st.columns(2)
    with c1:
        choice = st.radio("Network", list(options), index=2, horizontal=False)
    kind, oh = options[choice]
    assign = pre.copy() if kind == "pre" else solve(oh, FREIGHT0)[0]
    with c2:
        down = st.selectbox("Warehouse to shut", sorted(assign.site.unique()),
                            index=sorted(assign.site.unique()).index("Delhi") if "Delhi" in assign.site.values else 0)

    f0, t0, km0, _ = evaluate(assign, FREIGHT0)
    alive = [s for s in assign.site.unique() if s != down]
    hit = assign.site == down
    after = assign.copy()
    after.loc[hit, "site"] = [road.loc[alive, c].idxmin() for c in assign.loc[hit, "city"]]
    f1, t1, km1, _ = evaluate(after, FREIGHT0)
    inc = ((f1 + t1) / (f0 + t0) - 1) * 100

    readout([
        (f"{inc:+.1f}%".replace("-", "−"), "change in annual cost", "bad" if inc > 0 else "good"),
        (f"{int(hit.sum())}", "cities rerouted", ""),
        (f"{km0:.0f} → {km1:.0f} km", "average trip", ""),
    ])

    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(network_map(after, closed=(down,)), width="stretch", config={"displayModeBar": False})
    with right:
        st.markdown(f"### Where {down}'s cities go")
        moved = assign.loc[hit, ["city"]].assign(**{"New warehouse": after.loc[hit, "site"].values})
        moved["Extra km"] = [road.loc[n, c] - road.loc[down, c] for c, n in zip(moved.city, moved["New warehouse"])]
        st.dataframe(moved.rename(columns={"city": "City"}).round(0), hide_index=True, width="stretch")
        try:
            allf = pd.read_csv("outputs/resilience_all_failures.csv")
            name = {"Before GST (18 sites)": "Pre-GST", "Spread out (21 sites)": "Post-GST ₹0 cr",
                    "Balanced (17 sites)": "Post-GST ₹0.5 cr", "Consolidated (11 sites)": "Post-GST ₹2 cr"}[choice]
            sub = allf[allf.network.str.startswith(name)].sort_values("cost_increase_%", ascending=False).head(5)
            st.markdown("### Most critical sites")
            st.dataframe(sub[["failed_dc", "cost_increase_%"]].rename(columns={"failed_dc": "Site", "cost_increase_%": "Cost change %"}),
                         hide_index=True, width="stretch")
        except FileNotFoundError:
            pass


def page_method():
    hero("Data and method", "Every number comes from a public source, except the per-site running cost, "
         "which is left for you to set.")
    st.markdown("""
<table class='cmp'>
<tr><th>Input</th><th>Value used</th><th>Source</th></tr>
<tr><td>Cities</td><td>52 urban areas over 1 million people</td><td>Census of India 2011, final figures</td></tr>
<tr><td>Demand per person</td><td>19.7 kg of edible oil a year</td><td>NITI Aayog, edible oils report (2024)</td></tr>
<tr><td>Company size</td><td>18.3% market share, about 22 million t national demand</td><td>ICICI Direct, Adani Wilmar IPO review (2022)</td></tr>
<tr><td>Warehouse size</td><td>Built in 20,000 sq ft blocks, the market leader's average depot</td><td>ICICI Direct (2022)</td></tr>
<tr><td>Rent</td><td>Median Grade A rent across 199 clusters in 21 markets</td><td>Knight Frank, India Warehousing Market Report 2026</td></tr>
<tr><td>Running a warehouse</td><td>0.92 × rent for handling and operations</td><td>IIM figures cited by Knight Frank (2018)</td></tr>
<tr><td>Road distances</td><td>Actual driving km for 27 × 52 routes</td><td>OSRM routing on OpenStreetMap</td></tr>
<tr><td>Trucking</td><td>₹5 per tonne-km</td><td>32 ft truck market rates (2026); DPIIT study as the low case</td></tr>
</table>""", unsafe_allow_html=True)
    st.markdown("""
## How it works
1. **Before GST.** Each city is served by its own state's warehouse.
2. **After GST.** A mixed-integer program chooses which of 27 sites to open, how big to build each one, and which warehouse serves each city, at the lowest total cost.
3. **Safety stock.** Compared using the square-root law: pooling demand at fewer sites needs less buffer stock.
4. **Stress test.** Each warehouse is shut in turn and its cities are rerouted to the nearest open one.

## What it leaves out
- Kerala, Andhra Pradesh, Jharkhand, Chhattisgarh and J&K have no published rent, so they borrow the nearest covered market's rate.
- Census 2011 is the most recent census, so populations are used as relative weights.
- Only warehouse-to-city trucking is modelled, not refinery-to-warehouse.
""")
    st.markdown("## Download the data")
    c = st.columns(3)
    for col, (label, path) in zip(c, [("Cities", "data/raw/cities_census2011.csv"),
                                      ("Rents by cluster", "data/raw/kf_rent_clusters_2025.csv"),
                                      ("Candidate sites", "data/raw/candidate_sites.csv")]):
        with open(path, "rb") as fh:
            col.download_button(f"Download {label.lower()}", fh, file_name=path.split("/")[-1], mime="text/csv")
    st.markdown("<p class='muted'>Built by Nalluri Sanjay, IIT Kharagpur. "
                "<a href='https://github.com/SanjayNalluri'>GitHub</a>, "
                "<a href='https://www.linkedin.com/in/sanjaynalluri2405/'>LinkedIn</a></p>", unsafe_allow_html=True)


nav = st.navigation([st.Page(page_finding, title="The finding", default=True),
                     st.Page(page_design, title="Design a network", url_path="design"),
                     st.Page(page_stress, title="Stress test", url_path="stress-test"),
                     st.Page(page_method, title="Data & method", url_path="method")],
                    position="top")
nav.run()
