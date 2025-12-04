import streamlit as st
import requests
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely import wkt

st.set_page_config(page_title="HOT AOI Building Overlap Detector")
st.title("HOT AOI Overlapping Buildings")

# 1️⃣ User input for HOT Task ID

task_id = st.text_input("Enter HOT Tasking Manager Task ID:")

if st.button("Run Query") and task_id:
# Fetch task details from HOT
with st.spinner("Fetching task details from HOT..."):
try:
hot_url = f"[https://tasks.hotosm.org/api/v2.0/tasks/{task_id}](https://tasks.hotosm.org/api/v2.0/tasks/{task_id})"
r = requests.get(hot_url, timeout=30)
r.raise_for_status()
task_json = r.json()

```
        # Extract bounding box
        if "bbox" in task_json:
            w, s, e, n = task_json["bbox"]
        else:
            coords = task_json["geometry"]["coordinates"][0]
            lons, lats = zip(*coords)
            w, s, e, n = min(lons), min(lats), max(lons), max(lats)
    except Exception as ex:
        st.error(f"Failed to fetch task or parse geometry: {ex}")
        st.stop()

# Query Postpass for overlapping buildings
with st.spinner("Querying Postpass for overlapping buildings..."):
    try:
        sql = f"""
        SELECT a.osm_id AS building_a, b.osm_id AS building_b, 
               ST_AsText(ST_Intersection(a.geom, b.geom)) AS geom_wkt
        FROM postpass_polygon AS a
        JOIN postpass_polygon AS b
          ON a.osm_id < b.osm_id
         AND a.tags ? 'building'
         AND b.tags ? 'building'
         AND a.geom && b.geom
         AND ST_Overlaps(a.geom, b.geom)
        WHERE a.geom && ST_MakeEnvelope({w},{s},{e},{n},4326)
        """
        response = requests.post(
            "https://postpass.geofabrik.de/api/0.2/interpreter",
            data={"data": sql, "options[geojson]": "false"},
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
    except Exception as ex:
        st.error(f"Postpass query failed: {ex}")
        st.stop()

    if not data:
        st.warning("No overlapping buildings found in this AOI.")
    else:
        # Convert WKT to GeoDataFrame
        gdf = gpd.GeoDataFrame(
            data, 
            geometry=gpd.GeoSeries.from_wkt([f["geom_wkt"] for f in data])
        )

        # Map preview
        m = folium.Map(location=[(s+n)/2, (w+e)/2], zoom_start=16)
        folium.GeoJson(gdf).add_to(m)
        st.subheader("Map Preview")
        st_folium(m, width=700, height=500)

        # Download button
        geojson_str = gdf.to_json()
        st.download_button(
            label="Download GeoJSON",
            data=geojson_str,
            file_name=f"overlapping_buildings_task_{task_id}.geojson",
            mime="application/geo+json"
        )
```
