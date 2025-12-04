import streamlit as st
import requests
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import json

st.set_page_config(page_title="Overlapping Buildings Detector")
st.title("Overlapping Buildings in BBOX using Postpass")

# BBOX input - single text field for all coordinates
st.subheader("Enter BBOX coordinates")
st.write("Enter coordinates as: [west, south, east, north] or west,south,east,north")
bbox_input = st.text_input("BBOX", value="98.041992,2.602864,98.052979,2.613839")

# Query button
if st.button("Find Overlapping Buildings") and bbox_input:
    # Parse the BBOX input
    try:
        # Remove brackets if present and split by commas
        bbox_input = bbox_input.strip("[](){} ")
        bbox_parts = bbox_input.split(",")
        
        if len(bbox_parts) != 4:
            st.error("Please enter exactly 4 coordinates: west, south, east, north")
            st.stop()
            
        west, south, east, north = [float(coord.strip()) for coord in bbox_parts]
        
        # Validate coordinates
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            st.error("Longitude must be between -180 and 180")
            st.stop()
        if not (-90 <= south <= 90 and -90 <= north <= 90):
            st.error("Latitude must be between -90 and 90")
            st.stop()
        if west >= east:
            st.error("West must be less than East")
            st.stop()
        if south >= north:
            st.error("South must be less than North")
            st.stop()
            
    except ValueError:
        st.error("Please enter valid numeric coordinates")
        st.stop()
    
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
            LIMIT 1000
            """
            
            # Fixed: Properly format the POST data
            post_data = {
                "data": sql
            }
            
            response = requests.post(
                "https://postpass.geofabrik.de/api/0.2/interpreter",
                data=post_data,
                timeout=120
            )
            response.raise_for_status()
            
            # Check if response contains data
            result = response.json()
            
            # Debug: Show raw response
            st.write("Query successful!")
            
        except requests.exceptions.RequestException as e:
            st.error(f"Network error: {e}")
            st.stop()
        except ValueError as e:
            st.error(f"Invalid JSON response: {e}")
            st.write(f"Raw response: {response.text[:500]}")
            st.stop()
        except Exception as ex:
            st.error(f"Postpass query failed: {ex}")
            st.stop()
    
    # Process the response
    if "results" not in result or not result["results"]:
        st.warning("No overlapping buildings found in this BBOX.")
        st.info(f"BBOX used: west={west}, south={south}, east={east}, north={north}")
    else:
        try:
            # Extract data from the response
            data = result["results"]
            
            # Create a list of geometries from WKT strings
            geometries = []
            features_data = []
            
            for item in data:
                if "geom_wkt" in item:
                    # Convert WKT to geometry
                    import shapely.wkt
                    geom = shapely.wkt.loads(item["geom_wkt"])
                    geometries.append(geom)
                    
                    # Store feature data
                    feature_item = item.copy()
                    feature_item.pop("geom_wkt", None)
                    features_data.append(feature_item)
            
            if not geometries:
                st.warning("No valid geometries found in the response.")
                st.stop()
            
            # Create GeoDataFrame
            gdf = gpd.GeoDataFrame(
                features_data,
                geometry=geometries,
                crs="EPSG:4326"
            )
            
            # Create map
            center_lat = (south + north) / 2
            center_lon = (west + east) / 2
            
            m = folium.Map(location=[center_lat, center_lon], zoom_start=16)
            
            # Add bounding box to map for reference
            folium.Rectangle(
                bounds=[[south, west], [north, east]],
                color='blue',
                fill=False,
                weight=2,
                opacity=0.5,
                tooltip="Search BBOX"
            ).add_to(m)
            
            # Add overlapping buildings
            folium.GeoJson(
                gdf,
                name="Overlapping Areas",
                tooltip=folium.GeoJsonTooltip(
                    fields=['building_a', 'building_b'],
                    aliases=['Building A ID:', 'Building B ID:']
                )
            ).add_to(m)
            
            folium.LayerControl().add_to(m)
            
            # Display map
            st.subheader(f"Found {len(gdf)} overlapping areas")
            st_folium(m, width=700, height=500)
            
            # Display data table
            st.subheader("Overlapping Building Pairs")
            st.dataframe(gdf[['building_a', 'building_b']])
            
            # Download button
            geojson_str = gdf.to_json()
            st.download_button(
                label="Download GeoJSON",
                data=geojson_str,
                file_name=f"overlapping_buildings_{west}_{south}_{east}_{north}.geojson",
                mime="application/geo+json"
            )
            
        except Exception as e:
            st.error(f"Error processing data: {e}")
            st.write("Debug info - response structure:")
            st.json(result)

# Add instructions
with st.expander("How to use"):
    st.write("""
    1. Enter BBOX coordinates in one of these formats:
       - `98.041992,2.602864,98.052979,2.613839`
       - `[98.041992, 2.602864, 98.052979, 2.613839]`
       - `(98.041992, 2.602864, 98.052979, 2.613839)`
    
    2. Click "Find Overlapping Buildings"
    
    3. The map will show:
       - Blue rectangle: Your search area
       - Colored shapes: Overlapping areas between buildings
    
    4. You can download the results as GeoJSON
    
    **Note:** The query is limited to 1000 results for performance.
    """)
