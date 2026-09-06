import geopandas as gpd

bridges = gpd.read_file('bridges.geojson')          # load the file

# drop the one row with the broken coordinate
bridges_clean = bridges[bridges['name'] != 'Thulo bharkhu'].copy()

bridges_clean.to_file('bridges_clean.geojson', driver='GeoJSON')  # save result

villages = gpd.read_file('populated_places.geojson')

# keep only rows where 'place' column says village or hamlet
villages = villages[villages['place'].isin(['village', 'hamlet'])].copy()

# turn shapes (polygons) into a single center point
villages['geometry'] = villages.geometry.centroid

# pick the best available name: English > Latin-spelling > native script
villages['display_name'] = villages['name_latin'].fillna(villages['name_en']).fillna(villages['name'])

# keep only the columns we actually need
villages_clean = villages[['display_name', 'place', 'adm2_name', 'adm3_name', 'geometry']].reset_index(drop=True)

villages_clean.to_file('villages_clean.geojson', driver='GeoJSON')

health = gpd.read_file('health_facilities.geojson')
health['geometry'] = health.geometry.centroid
health['display_name'] = health['name_latin'].fillna(health['name_en']).fillna(health['name']).fillna(health['amenity'])
health_clean = health[['display_name', 'amenity', 'adm2_name', 'geometry']].reset_index(drop=True)
health_clean.to_file('health_clean.geojson', driver='GeoJSON')

roads = gpd.read_file('roads.gpkg')

# only keep line-shaped roads, drop stray points/polygons
roads = roads[roads.geometry.geom_type == 'LineString'].copy()

vehicle_types = ['trunk','primary','secondary','tertiary','residential','service','unclassified']
foot_types = ['path','track','footway','steps','pedestrian']

def tag_mode(h):
    if h in vehicle_types:
        return 'vehicle'
    if h in foot_types:
        return 'foot'
    return 'other'

# apply that function to every row's 'highway' column, make a new 'mode' column
roads['mode'] = roads['highway'].apply(tag_mode)

roads_clean = roads[['id','highway','mode','surface','bridge','adm2_name','geometry']].reset_index(drop=True)
roads_clean.to_file('roads_clean.geojson', driver='GeoJSON')



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

# ---------- 2. FIXED: proper name fallback (no more blank/duplicate names) ----------
def make_name(row):
    if pd.notna(row['display_name']) and str(row['display_name']).strip() != '':
        return row['display_name']
    elif pd.notna(row['adm3_name']):
        return f"{row['adm3_name']} area"
    else:
        return "Unnamed village"

villages['final_name'] = villages.apply(make_name, axis=1)
# if two villages ended up with the same name, add their row number to tell them apart
dupe_mask = villages['final_name'].duplicated(keep=False)
villages.loc[dupe_mask, 'final_name'] = (
    villages.loc[dupe_mask, 'final_name'] + " #" + villages.loc[dupe_mask].index.astype(str)
)

# ---------- 3. Mark road segments broken by washed-out bridges ----------
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
print(f"Roads broken by washed-out bridges: {roads['broken'].sum()} / {len(roads)}")

# ---------- 4. Snap-merge nearby road endpoints ----------
all_coords = []
for _, road in usable_roads.iterrows():
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

def snap(pt):
    return coord_to_snapped.get(tuple(pt), tuple(pt))

# ---------- 5. Build the road network graph ----------
G = nx.Graph()
for _, road in usable_roads.iterrows():
    coords = list(road.geometry.coords)
    for i in range(len(coords) - 1):
        p1, p2 = snap(coords[i]), snap(coords[i + 1])
        if p1 == p2:
            continue
        dist = Point(p1).distance(Point(p2))
        G.add_edge(p1, p2, weight=dist)

print(f"Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
print(f"Separate disconnected networks: {nx.number_connected_components(G)}")

# ---------- 6. Snap villages & hospitals onto the nearest graph node ----------
graph_nodes = np.array(list(G.nodes))
node_tree = cKDTree(graph_nodes)

def snap_to_graph(pt):
    dist, idx = node_tree.query((pt.x, pt.y))
    return tuple(graph_nodes[idx]), dist

MAX_SNAP_DIST = 500
for df in (villages, health):
    df['snap_node'] = None
    df['snap_dist'] = None
    for i, row in df.iterrows():
        node, dist = snap_to_graph(row.geometry)
        df.at[i, 'snap_node'] = node
        df.at[i, 'snap_dist'] = dist

# ---------- 7. For each village, find the nearest reachable hospital ----------
results = []
for i, v in villages.iterrows():
    name = v['final_name']
    if v['snap_dist'] > MAX_SNAP_DIST:
        results.append({'village': name, 'district': v['adm2_name'],
                         'nearest_hospital': None, 'distance_km': None,
                         'status': 'No nearby road mapped'})
        continue

    best_dist, best_h = float('inf'), None
    for j, h in health.iterrows():
        try:
            d = nx.shortest_path_length(G, v['snap_node'], h['snap_node'], weight='weight')
            d += v['snap_dist'] + h['snap_dist']
            if d < best_dist:
                best_dist, best_h = d, h['display_name']
        except nx.NetworkXNoPath:
            continue

    if best_h is None:
        results.append({'village': name, 'district': v['adm2_name'],
                         'nearest_hospital': None, 'distance_km': None,
                         'status': 'ISOLATED - no route to any hospital'})
    else:
        results.append({'village': name, 'district': v['adm2_name'],
                         'nearest_hospital': best_h, 'distance_km': round(best_dist / 1000, 1),
                         'status': 'Reachable'})

# ---------- 8. Save results ----------
df = pd.DataFrame(results)
print(df['status'].value_counts())
print("Missing village names:", df['village'].isna().sum())
df.to_csv('village_hospital_access.csv', index=False)

# ---------- 9. Also save villages_clean.geojson with the fixed name added,
#              so map.py can use 'final_name' for matching ----------
villages_wgs = gpd.read_file('villages_clean.geojson')
villages_wgs['final_name'] = villages['final_name'].values
villages_wgs.to_file('villages_clean.geojson', driver='GeoJSON')

print("Saved: village_hospital_access.csv and updated villages_clean.geojson")