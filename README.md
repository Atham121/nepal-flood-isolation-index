# Nepal Flood Isolation Index

Identifies flood-isolated villages in Nepal by combining bridge damage, road network and health facility data into a priority-ranked map for relief response.

## Problem
After floods wash out bridges, villages can be cut off from hospitals and aid. Relief teams need to know which villages to reach first.

## Approach
1. **Clean data:** bridges, roads, villages and health facilities (`*_clean.geojson`)
2. **Break the network:** roads within 30 m of a washed-out bridge are marked unusable
3. **Build two road graphs** (NetworkX): vehicle-only, and vehicle + foot paths. Tiny OpenStreetMap gaps are snapped together (2 m tolerance)
4. **Check access:** shortest route from each village to the nearest hospital or health facility, by car and on foot
5. **Classify** each village: car-reachable, walkable only, or isolated
6. **Score priority** (0-10) from three factors:
   - Access status (50%): isolated scores highest
   - Washed-out bridges within 3 km (30%)
   - Distance to nearest hospital (20%)
7. **Label** the score: HIGH (7+), MEDIUM (4-7), LOW (below 4)

## Tech stack
Python, GeoPandas, NetworkX, SciPy, Shapely, Pandas, NumPy, Folium

## Maps
- `flood_access_map.html`: reachable vs. isolated villages
- `flood_priority_map.html`: HIGH / MEDIUM / LOW priority villages

Download the repo and open either file in a browser to explore the interactive maps.

| File | Purpose |
|---|---|
| `code.py` / `step3_v2.py` | Builds road graphs and checks village-to-hospital access |
| `step4_priority.py` | Scores and ranks villages by priority |
| `map.py` | Access map (reachable vs. isolated) |
| `polish.py` | Priority map and final cleaned report |

## Data sources
- **OpenStreetMap or google map:** roads, villages and health facilities
- **Nepal Open Data Portal:** flood-affected areas, roads and bridge status

## Limitations
The data was collected over a span of about two weeks during the flood period. Bridge status, road conditions and village locations may be incomplete, outdated or inaccurate. Results are intended as a prioritization aid and should be verified on the ground before any relief decisions.

## Future work
Add population weighting, real-time flood data, and helipad-based aid routing.



THIS IS THE PRIORITY MAP
<img width="1910" height="917" alt="image" src="https://github.com/user-attachments/assets/651c539d-b9c0-4f88-82e8-abcde28b0826" />

THIS IS THE ACCESS MAP
<img width="1912" height="915" alt="image" src="https://github.com/user-attachments/assets/27e19010-f02d-45ef-b388-58e54bd3c442" />




