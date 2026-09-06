import geopandas as gpd
import pandas as pd
import folium

# ---------- Load data ----------
villages = gpd.read_file('villages_clean.geojson')   # lat/lon version for mapping
health = gpd.read_file('health_clean.geojson')
bridges = gpd.read_file('bridges_clean.geojson')
priority = pd.read_csv('village_priority_ranked.csv')

# Merge village geometry with priority results
merged = villages.merge(priority, left_on='final_name', right_on='village', how='left')

# ---------- Base map ----------
center_lat = villages.geometry.y.mean()
center_lon = villages.geometry.x.mean()
m = folium.Map(location=[center_lat, center_lon], zoom_start=10, tiles='OpenStreetMap')

# ---------- Priority color mapping ----------
priority_colors = {'HIGH': 'red', 'MEDIUM': 'orange', 'LOW': 'green'}

for _, row in merged.iterrows():
    if pd.isna(row.geometry.y) or pd.isna(row.get('priority')):
        continue

    color = priority_colors.get(row['priority'], 'gray')
    radius = 10 if row['priority'] == 'HIGH' else 7  # make HIGH priority visually bigger

    popup_text = f"""
    <b>{row['village']}</b><br>
    District: {row['district']}<br>
    Priority: <b>{row['priority']}</b> (score: {row['priority_score']:.1f})<br>
    Status: {row['summary']}<br>
    Nearby broken bridges: {row['nearby_broken_bridges']}
    """
    folium.CircleMarker(
        location=[row.geometry.y, row.geometry.x],
        radius=radius,
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.85,
        popup=folium.Popup(popup_text, max_width=280)
    ).add_to(m)

# ---------- Hospitals ----------
for _, row in health.iterrows():
    folium.Marker(
        location=[row.geometry.y, row.geometry.x],
        popup=f"<b>{row['display_name']}</b><br>Type: {row['amenity']}",
        icon=folium.Icon(color='blue', icon='plus', prefix='fa')
    ).add_to(m)

# ---------- Washed-out bridges ----------
washed_out = bridges[bridges['status'] == 'Washed out']
for _, row in washed_out.iterrows():
    folium.Marker(
        location=[row.geometry.y, row.geometry.x],
        popup=f"<b>{row['name']}</b><br>Status: Washed out",
        icon=folium.Icon(color='black', icon='remove', prefix='fa')
    ).add_to(m)

# ---------- Legend ----------
legend_html = '''
<div style="position: fixed; bottom: 30px; left: 30px; z-index:9999; background:white;
            padding:12px; border:2px solid grey; border-radius:5px; font-size:14px;">
<b>Village Priority</b><br>
🔴 HIGH priority (check first)<br>
🟠 MEDIUM priority<br>
🟢 LOW priority<br>
🔵 Hospital / Health facility<br>
⚫ Washed-out bridge<br>
</div>
'''
m.get_root().html.add_child(folium.Element(legend_html))

m.save('flood_priority_map.html')
print("Saved: flood_priority_map.html")

# ---------- Clean up final CSV for readability ----------
final_clean = priority.rename(columns={
    'village': 'Village',
    'district': 'District',
    'summary': 'Access Status',
    'nearby_broken_bridges': 'Nearby Broken Bridges',
    'priority_score': 'Priority Score',
    'priority': 'Priority Level'
})
final_clean.to_csv('FINAL_village_priority_report.csv', index=False)
print("Saved: FINAL_village_priority_report.csv")