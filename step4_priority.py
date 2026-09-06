import geopandas as gpd
import pandas as pd
import numpy as np

# Load what we already have
villages = gpd.read_file('villages_clean.geojson').to_crs(32645)
bridges = gpd.read_file('bridges_clean.geojson').to_crs(32645)
results = pd.read_csv('village_hospital_access_v2.csv')

washed_out = bridges[bridges['status'] == 'Washed out']

# ---------- 1. Count nearby washed-out bridges per village (within 3km) ----------
RADIUS_M = 3000
nearby_broken_counts = []
for _, v in villages.iterrows():
    count = (washed_out.geometry.distance(v.geometry) <= RADIUS_M).sum()
    nearby_broken_counts.append(count)
villages['nearby_broken_bridges'] = nearby_broken_counts

# Merge into results using village name
merged = results.merge(
    villages[['final_name', 'nearby_broken_bridges']],
    left_on='village', right_on='final_name', how='left'
)

# ---------- 2. Score each factor (0-10 scale) ----------
def access_score(row):
    if 'ISOLATED' in row['summary']:
        return 10
    elif 'walkable only' in row['summary']:
        return 6
    else:
        return 2

def distance_score(row):
    km = row['vehicle_km'] if pd.notna(row['vehicle_km']) else row['foot_km']
    if pd.isna(km):
        return 10          # no distance found = worst case
    return min(km / 5, 10)  # every 5km adds 1 point, capped at 10

def bridge_score(row):
    return min(row['nearby_broken_bridges'] * 2, 10)  # each nearby broken bridge = +2, capped at 10

merged['access_score'] = merged.apply(access_score, axis=1)
merged['distance_score'] = merged.apply(distance_score, axis=1)
merged['bridge_score'] = merged.apply(bridge_score, axis=1)

# ---------- 3. Weighted final priority score ----------
# Access matters most (cut off = worst), then bridge damage, then distance
merged['priority_score'] = (
    merged['access_score'] * 0.5 +
    merged['bridge_score'] * 0.3 +
    merged['distance_score'] * 0.2
)

# ---------- 4. Convert to simple labels ----------
def priority_label(score):
    if score >= 7:
        return 'HIGH'
    elif score >= 4:
        return 'MEDIUM'
    else:
        return 'LOW'

merged['priority'] = merged['priority_score'].apply(priority_label)

# ---------- 5. Sort and save ----------
final = merged[['village','district','summary','nearby_broken_bridges',
                'priority_score','priority']].sort_values('priority_score', ascending=False)

print(final['priority'].value_counts())
print()
print(final.head(15).to_string(index=False))

final.to_csv('village_priority_ranked.csv', index=False)
print("\nSaved: village_priority_ranked.csv")