import streamlit as st
import requests
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely import wkt

st.set_page_config(page_title="Overlapping Buildings Detector")
st.title("Overlapping Buildings in BBOX using Postpass")

# 1️⃣ User input for bounding box coordinates (single column)

st.subheader("Enter BBOX coordinates")
west = st.number_input("West (min longitude)", value=0.0, format="%.6f")
south = st.number_input("South (min latitude)", value=0.0, format="%.6f")
east = st.number_input("East (max longitude)", value=0.01, format="%.6f")
north = st.number_input("North (max latitude)", value=0.01, format="%.6f")

# 2️⃣ Query Postpass for overlapping buildings

if st.button("Find Overlapping Buildings"):
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
WHERE a.geom && ST_MakeEnvelope({west},{south},{east},{north},4326)
"""

```
        response = requests.post(
            "https://postpass.geofabrik.de/api/0.2/interpreter",
            data={"data": sql, "options[geojson]": "false"},
            timeout=120
        )
        response.raise_for_status()
        data = response.json()
    except Exception as ex:
        st.error(f"Postpass query failed: {ex}")
        st.stop()

    if len(data) == 0:
        st.warning("No overlapping buildings found in this BBOX.")
    else:
        # Convert WKT to GeoDataFrame
        gdf = gpd.GeoDataFrame(
            data,
            geometry=gpd.GeoSeries.from_wkt([f["geom_wkt"] for f in data])
        )

        # Map preview
        m = folium.Map(location=[(south+north)/2, (west+east)/2], zoom_start=16)
        folium.GeoJson(gdf, name="Overlapping Buildings").add_to(m)
        st.subheader("Map Preview")
        st_folium(m, width=700, height=500)

        # Download button
        geojson_str = gdf.to_json()
        st.download_button(
            label="Download GeoJSON",
            data=geojson_str,
            file_name=f"overlapping_buildings_{west}_{south}_{east}_{north}.geojson",
            mime="application/geo+json"
        )
```
