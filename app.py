import streamlit as st
import requests
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely import wkt
import json

st.set_page_config(page_title="HOT AOI Building Overlap Detector")
st.title("HOT AOI Overlapping Buildings")

# 1️⃣ User input for HOT Task ID
task_id = st.text_input("Enter HOT Tasking Manager Task ID:", placeholder="e.g., 12345")

if st.button("Run Query") and task_id:
    # Fetch task details from HOT
    with st.spinner("Fetching task details from HOT..."):
        try:
            # First, get task details to find project ID
            hot_url = f"https://tasks.hotosm.org/api/v2.0/tasks/{task_id}"
            r = requests.get(hot_url, timeout=30)
            r.raise_for_status()
            task_json = r.json()
            
            # Get project ID from task
            project_id = task_json.get("projectId")
            
            if not project_id:
                st.error("Could not find project ID for this task")
                st.stop()
            
            # Now get AOI geometry using the correct API endpoint
            aoi_url = f"https://tasking-manager-production-api.hotosm.org/api/v2/projects/{project_id}/queries/aoi/?as_file=true"
            aoi_response = requests.get(aoi_url, timeout=30)
            aoi_response.raise_for_status()
            
            # Parse the AOI GeoJSON
            aoi_geojson = aoi_response.json()
            
            # Extract bounding box from AOI geometry
            if aoi_geojson and "features" in aoi_geojson and len(aoi_geojson["features"]) > 0:
                geometry = aoi_geojson["features"][0]["geometry"]
                
                # Convert to shapely geometry to get bounds
                import shapely.geometry
                shape = shapely.geometry.shape(geometry)
                bounds = shape.bounds  # Returns (minx, miny, maxx, maxy)
                w, s, e, n = bounds
            else:
                # Fallback to task bbox if AOI not available
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

    # Display AOI info
    st.info(f"**Project ID:** {project_id}")
    st.info(f"**Bounding Box:** West={w:.5f}, South={s:.5f}, East={e:.5f}, North={n:.5f}")
    
    # Option to download the AOI itself
    st.subheader("AOI Download")
    st.download_button(
        label="Download AOI GeoJSON",
        data=json.dumps(aoi_geojson),
        file_name=f"aoi_project_{project_id}.geojson",
        mime="application/geo+json"
    )

    if len(data) == 0:
        st.warning("No overlapping buildings found in this AOI.")
    else:
        st.success(f"Found {len(data)} overlapping building pairs!")
        
        # Convert WKT to GeoDataFrame
        gdf = gpd.GeoDataFrame(
            data, 
            geometry=gpd.GeoSeries.from_wkt([f["geom_wkt"] for f in data])
        )

        # Map preview with both AOI and overlaps
        m = folium.Map(location=[(s+n)/2, (w+e)/2], zoom_start=16)
        
        # Add AOI boundary
        folium.GeoJson(
            aoi_geojson,
            style_function=lambda x: {
                'fillColor': 'blue',
                'color': 'blue',
                'weight': 2,
                'fillOpacity': 0.1
            },
            name="AOI Boundary"
        ).add_to(m)
        
        # Add overlapping buildings
        folium.GeoJson(
            gdf,
            style_function=lambda x: {
                'fillColor': 'red',
                'color': 'red',
                'weight': 2,
                'fillOpacity': 0.7
            },
            name="Overlapping Buildings"
        ).add_to(m)
        
        folium.LayerControl().add_to(m)
        
        st.subheader("Map Preview")
        st_folium(m, width=700, height=500)

        # Download button for overlaps
        geojson_str = gdf.to_json()
        st.download_button(
            label="Download Overlaps GeoJSON",
            data=geojson_str,
            file_name=f"overlapping_buildings_task_{task_id}_project_{project_id}.geojson",
            mime="application/geo+json"
        )
        
        # Show data table
        st.subheader("Overlapping Building Pairs")
        st.dataframe(gdf[['building_a', 'building_b']], use_container_width=True)
