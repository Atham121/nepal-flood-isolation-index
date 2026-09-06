import geopandas as gpd
import pandas as pd
import folium

# ---------- Load data (original lat/lon version, not the UTM one) ----------
villages = gpd.read_file('villages_clean.geojson')       # EPSG:4326 (lat/lon) - good for maps
health = gpd.read_file('health_clean.geojson')
bridges = gpd.read_file('bridges_clean.geojson')
results = pd.read_csv('village_hospital_access.csv')

# Merge village geometry with their reachability status
villages = villages.reset_index(drop=True)
villages['display_name_clean'] = villages['display_name'].fillna(villages['adm3_name'])
merged = villages.merge(results, left_on='final_name', right_on='village', how='left')

# ---------- Create the base map, centered on the flood area ----------
center_lat = villages.geometry.y.mean()
center_lon = villages.geometry.x.mean()
m = folium.Map(location=[center_lat, center_lon], zoom_start=10, tiles='OpenStreetMap')

# ---------- Add villages, color-coded ----------
for _, row in merged.iterrows():
    if pd.isna(row.geometry.y):
        continue
    status = row.get('status', 'Unknown')
    if status == 'Reachable':
        color = 'green'
    elif isinstance(status, str) and 'ISOLATED' in status:
        color = 'red'
    else:
        color = 'gray'

    popup_text = f"""
    <b>{row['display_name_clean']}</b><br>
    District: {row.get('district', row['adm2_name'])}<br>
    Status: {status}<br>
    Nearest hospital: {row.get('nearest_hospital', 'N/A')}<br>
    Distance: {row.get('distance_km', 'N/A')} km
    """
    folium.CircleMarker(
        location=[row.geometry.y, row.geometry.x],
        radius=7,
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.8,
        popup=folium.Popup(popup_text, max_width=250)
    ).add_to(m)

# ---------- Add hospitals (blue markers) ----------
for _, row in health.iterrows():
    folium.Marker(
        location=[row.geometry.y, row.geometry.x],
        popup=f"<b>{row['display_name']}</b><br>Type: {row['amenity']}",
        icon=folium.Icon(color='blue', icon='plus', prefix='fa')
    ).add_to(m)

# ---------- Add washed-out bridges (X markers) ----------
washed_out = bridges[bridges['status'] == 'Washed out']
for _, row in washed_out.iterrows():
    folium.Marker(
        location=[row.geometry.y, row.geometry.x],
        popup=f"<b>{row['name']}</b><br>Status: Washed out",
        icon=folium.Icon(color='black', icon='remove', prefix='fa')
    ).add_to(m)

# ---------- Add a legend ----------
legend_html = '''
<div style="position: fixed; bottom: 30px; left: 30px; z-index:9999; background:white;
            padding:10px; border:2px solid grey; border-radius:5px; font-size:14px;">
<b>Legend</b><br>
🟢 Village - Reachable<br>
🔴 Village - Isolated<br>
🔵 Hospital / Health facility<br>
⚫ Washed-out bridge<br>
</div>
'''
m.get_root().html.add_child(folium.Element(legend_html))

# ---------- Save ----------
m.save('flood_access_map.html')
print("Map saved as flood_access_map.html — open it in your browser.")