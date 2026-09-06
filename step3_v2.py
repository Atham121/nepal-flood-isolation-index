import geopandas as gpd
import networkx as nx
from shapely.geometry import Point
import numpy as np
from scipy.spatial import cKDTree
import pandas as pd

# ---------- 1. Load cleaned data ----------
roads = gpd.read_file('roads_clean.geojson').to_crs(32645)
bridges = gpd.read_file('bridges_clean.geojson').to_crs(32645)
villages = gpd.read_file('villages_clean.geojson').to_crs(32645)
health = gpd.read_file('health_clean.geojson').to_crs(32645)

# ---------- 2. Fixed name logic (from Step 1) ----------
def make_name(row):
    if pd.notna(row['display_name']) and str(row['display_name']).strip() != '':
        return row['display_name']
    elif pd.notna(row['adm3_name']):
        return f"{row['adm3_name']} area"
    else:
        return "Unnamed village"

villages['final_name'] = villages.apply(make_name, axis=1)
dupe_mask = villages['final_name'].duplicated(keep=False)
villages.loc[dupe_mask, 'final_name'] = (
    villages.loc[dupe_mask, 'final_name'] + " #" + villages.loc[dupe_mask].index.astype(str)
)

# ---------- 3. Mark roads broken by washed-out bridges ----------
washed_out = bridges[bridges['status'] == 'Washed out']
THRESHOLD_M = 30
broken_idx = set()
for idx, road in roads.iterrows():
    for _, b in washed_out.iterrows():
        if road.geometry.distance(b.geometry) <= THRESHOLD_M:
            broken_idx.add(idx)
            break
roads['broken'] = roads.index.isin(broken_idx)
usable_roads = roads[~roads['broken']].copy()

# ---------- 4. Build a snap-merge function (fixes tiny OSM gaps) ----------
def build_snap_function(roads_subset):
    all_coords = []
    for _, road in roads_subset.iterrows():
        all_coords.extend(list(road.geometry.coords))
    all_coords = np.array(list(set(all_coords)))

    SNAP_TOL = 2.0
    tree = cKDTree(all_coords)
    pairs = tree.query_pairs(r=SNAP_TOL)

    parent = list(range(len(all_coords)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py
    for a, b in pairs:
        union(a, b)

    cluster_rep = {}
    coord_to_snapped = {}
    for i, c in enumerate(all_coords):
        root = find(i)
        if root not in cluster_rep:
            cluster_rep[root] = tuple(all_coords[root])
        coord_to_snapped[tuple(c)] = cluster_rep[root]

    return lambda pt: coord_to_snapped.get(tuple(pt), tuple(pt))

def build_graph(roads_subset):
    snap = build_snap_function(roads_subset)
    G = nx.Graph()
    for _, road in roads_subset.iterrows():
        coords = list(road.geometry.coords)
        for i in range(len(coords) - 1):
            p1, p2 = snap(coords[i]), snap(coords[i + 1])
            if p1 == p2:
                continue
            dist = Point(p1).distance(Point(p2))
            G.add_edge(p1, p2, weight=dist)
    return G

# ---------- 5. Build TWO graphs: vehicle-only, and vehicle+foot combined ----------
vehicle_roads = usable_roads[usable_roads['mode'] == 'vehicle']
G_vehicle = build_graph(vehicle_roads)
G_all = build_graph(usable_roads)   # vehicle + foot combined

print(f"Vehicle-only graph: {G_vehicle.number_of_nodes()} nodes")
print(f"Vehicle+foot graph: {G_all.number_of_nodes()} nodes")

# ---------- 6. Snap villages/hospitals onto EACH graph separately ----------
MAX_SNAP_DIST = 500

def snap_all_points(df, G):
    graph_nodes = np.array(list(G.nodes))
    node_tree = cKDTree(graph_nodes)
    snap_nodes, snap_dists = [], []
    for _, row in df.iterrows():
        dist, idx = node_tree.query((row.geometry.x, row.geometry.y))
        snap_nodes.append(tuple(graph_nodes[idx]))
        snap_dists.append(dist)
    return snap_nodes, snap_dists

villages['v_node_vehicle'], villages['v_dist_vehicle'] = snap_all_points(villages, G_vehicle)
villages['v_node_all'], villages['v_dist_all'] = snap_all_points(villages, G_all)
health['h_node_vehicle'], health['h_dist_vehicle'] = snap_all_points(health, G_vehicle)
health['h_node_all'], health['h_dist_all'] = snap_all_points(health, G_all)

# ---------- 7. Reachability check helper ----------
def check_reachability(v_node, v_dist, health_df, node_col, dist_col, G):
    if v_dist > MAX_SNAP_DIST:
        return None, None, 'No nearby road mapped'
    best_dist, best_h = float('inf'), None
    for _, h in health_df.iterrows():
        try:
            d = nx.shortest_path_length(G, v_node, h[node_col], weight='weight')
            d += v_dist + h[dist_col]
            if d < best_dist:
                best_dist, best_h = d, h['display_name']
        except nx.NetworkXNoPath:
            continue
    if best_h is None:
        return None, None, 'ISOLATED'
    return best_h, round(best_dist / 1000, 1), 'Reachable'

# ---------- 8. Run both checks per village ----------
results = []
for i, v in villages.iterrows():
    veh_h, veh_km, veh_status = check_reachability(
        v['v_node_vehicle'], v['v_dist_vehicle'], health, 'h_node_vehicle', 'h_dist_vehicle', G_vehicle)
    all_h, all_km, all_status = check_reachability(
        v['v_node_all'], v['v_dist_all'], health, 'h_node_all', 'h_dist_all', G_all)

    # Combined honest summary
    if veh_status == 'Reachable':
        summary = f"Car-reachable ({veh_km} km)"
    elif all_status == 'Reachable':
        summary = f"No car route - walkable only ({all_km} km on foot)"
    else:
        summary = "ISOLATED - no route by car or foot"

    results.append({
        'village': v['final_name'],
        'district': v['adm2_name'],
        'vehicle_status': veh_status,
        'vehicle_hospital': veh_h,
        'vehicle_km': veh_km,
        'foot_status': all_status,
        'foot_hospital': all_h,
        'foot_km': all_km,
        'summary': summary
    })

df = pd.DataFrame(results)
print(df['summary'].apply(lambda s: s.split(' (')[0]).value_counts())
df.to_csv('village_hospital_access_v2.csv', index=False)
print("Saved: village_hospital_access_v2.csv")