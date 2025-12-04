import streamlit as st
import requests
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import json
import csv
from io import StringIO

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
            # Based on the Postpass examples, we need to use this format
            # First, let's try a simple test query to get buildings
            
            # Simple query to count buildings
            test_query = f"""SELECT 
                COUNT(*) as building_count 
                FROM postpass_polygon 
                WHERE tags ? 'building'
                AND geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)"""
            
            # Format as shown in examples
            formatted_query = f"""{{{{data:sql,server=https://postpass.geofabrik.de/api/0.2/,geojson=false}}}}
{test_query}"""
            
            st.write("Sending query to Postpass...")
            
            # Make the request - the examples show using GET with the query as a parameter
            # But let's try POST first as that's what we were doing
            response = requests.post(
                "https://postpass.geofabrik.de/api/0.2/interpreter",
                data={"data": test_query},
                timeout=120
            )
            
            st.write(f"Response status: {response.status_code}")
            st.write(f"Response headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                # Try to parse the response
                content = response.text.strip()
                
                # Check if it's JSON or CSV
                if content.startswith('[') or content.startswith('{'):
                    # JSON response
                    try:
                        data = json.loads(content)
                        st.write(f"JSON response: {data}")
                    except:
                        st.write(f"Could not parse as JSON: {content[:200]}")
                else:
                    # Probably CSV
                    try:
                        csv_reader = csv.reader(StringIO(content))
                        rows = list(csv_reader)
                        st.write(f"CSV response with {len(rows)} rows")
                        if rows:
                            st.write("First few rows:")
                            for i, row in enumerate(rows[:5]):
                                st.write(f"Row {i}: {row}")
                    except:
                        st.write(f"Raw response: {content[:500]}")
            
            # Now try the overlap query
            st.write("\n---\nTrying overlap detection query...")
            
            # Overlap query based on Postpass SQL examples
            overlap_query = f"""SELECT 
                a.osm_id as building_a,
                b.osm_id as building_b,
                ST_Area(ST_Intersection(a.geom, b.geom)::geography) as overlap_area_m2,
                ST_AsText(ST_Intersection(a.geom, b.geom)) as overlap_geom
                FROM postpass_polygon a
                JOIN postpass_polygon b 
                ON a.osm_id < b.osm_id 
                AND ST_Intersects(a.geom, b.geom)
                AND a.geom && b.geom
                WHERE a.tags ? 'building' 
                AND b.tags ? 'building'
                AND a.geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
                AND b.geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
                AND ST_Area(ST_Intersection(a.geom, b.geom)::geography) > 0.1
                LIMIT 100"""
            
            st.code(overlap_query, language='sql')
            
            response2 = requests.post(
                "https://postpass.geofabrik.de/api/0.2/interpreter",
                data={"data": overlap_query},
                timeout=120
            )
            
            st.write(f"Overlap query status: {response2.status_code}")
            
            if response2.status_code == 200:
                content2 = response2.text.strip()
                
                if content2:
                    # Try to parse as CSV
                    try:
                        csv_reader = csv.reader(StringIO(content2))
                        overlap_rows = list(csv_reader)
                        
                        if overlap_rows:
                            st.success(f"Found {len(overlap_rows)-1 if len(overlap_rows) > 1 else 0} overlapping building pairs")
                            
                            # Display as table
                            headers = overlap_rows[0] if len(overlap_rows) > 0 else ['building_a', 'building_b', 'overlap_area_m2', 'overlap_geom']
                            data_rows = overlap_rows[1:] if len(overlap_rows) > 1 else []
                            
                            if data_rows:
                                st.subheader("Overlapping Building Pairs")
                                
                                # Create a DataFrame for display
                                import pandas as pd
                                df = pd.DataFrame(data_rows, columns=headers)
                                st.dataframe(df)
                                
                                # Try to create a map if we have geometries
                                if 'overlap_geom' in headers:
                                    try:
                                        # Parse WKT geometries
                                        from shapely import wkt
                                        import geopandas as gpd
                                        
                                        geometries = []
                                        valid_rows = []
                                        
                                        for i, row in enumerate(data_rows):
                                            try:
                                                geom_wkt = row[headers.index('overlap_geom')]
                                                if geom_wkt and geom_wkt.lower() != 'null':
                                                    geom = wkt.loads(geom_wkt)
                                                    geometries.append(geom)
                                                    
                                                    # Create a dict for this row
                                                    row_dict = {}
                                                    for j, header in enumerate(headers):
                                                        if header != 'overlap_geom' and j < len(row):
                                                            row_dict[header] = row[j]
                                                    valid_rows.append(row_dict)
                                            except Exception as e:
                                                st.write(f"Could not parse geometry for row {i}: {e}")
                                        
                                        if geometries and valid_rows:
                                            # Create GeoDataFrame
                                            gdf = gpd.GeoDataFrame(
                                                valid_rows,
                                                geometry=geometries,
                                                crs="EPSG:4326"
                                            )
                                            
                                            # Create map
                                            center_lat = (south + north) / 2
                                            center_lon = (west + east) / 2
                                            
                                            m = folium.Map(location=[center_lat, center_lon], zoom_start=16)
                                            
                                            # Add bounding box
                                            folium.Rectangle(
                                                bounds=[[south, west], [north, east]],
                                                color='blue',
                                                fill=False,
                                                weight=2,
                                                opacity=0.5,
                                                tooltip="Search BBOX"
                                            ).add_to(m)
                                            
                                            # Add overlapping areas
                                            folium.GeoJson(
                                                gdf,
                                                name="Overlapping Areas",
                                                tooltip=folium.GeoJsonTooltip(
                                                    fields=['building_a', 'building_b', 'overlap_area_m2'],
                                                    aliases=['Building A:', 'Building B:', 'Overlap Area (m²):']
                                                ),
                                                style_function=lambda x: {
                                                    'fillColor': 'red',
                                                    'color': 'red',
                                                    'weight': 2,
                                                    'fillOpacity': 0.5
                                                }
                                            ).add_to(m)
                                            
                                            folium.LayerControl().add_to(m)
                                            
                                            # Display map
                                            st.subheader("Map of Overlapping Areas")
                                            st_folium(m, width=700, height=500)
                                            
                                            # Download button
                                            geojson_str = gdf.to_json()
                                            st.download_button(
                                                label="Download Overlaps as GeoJSON",
                                                data=geojson_str,
                                                file_name=f"overlapping_buildings_{west}_{south}_{east}_{north}.geojson",
                                                mime="application/geo+json"
                                            )
                                    except Exception as e:
                                        st.warning(f"Could not create map: {e}")
                                        st.write(f"Error details: {str(e)}")
                        else:
                            st.warning("No overlapping buildings found in this area.")
                    except Exception as e:
                        st.write(f"Could not parse response as CSV: {e}")
                        st.write(f"Raw response: {content2[:500]}")
                else:
                    st.warning("Empty response - no overlapping buildings found.")
            else:
                st.error(f"Overlap query failed: {response2.status_code}")
                st.write(f"Error: {response2.text[:500]}")
                
        except requests.exceptions.RequestException as e:
            st.error(f"Network error: {e}")
            if hasattr(e, 'response') and e.response:
                st.write(f"Error details: {e.response.text[:500]}")
        except Exception as ex:
            st.error(f"Query failed: {ex}")
            import traceback
            st.write(traceback.format_exc())

# Alternative: Try GET request approach
with st.expander("Try alternative GET request method"):
    if st.button("Test GET request method"):
        # Try the format from the examples
        test_get_query = f"""SELECT COUNT(*) as count FROM postpass_polygon WHERE tags ? 'building' LIMIT 5"""
        encoded_query = requests.utils.quote(test_get_query)
        
        # Try the format shown in examples: {{data:sql,server=...,geojson=false}}
        example_format = f"{{{{data:sql,server=https://postpass.geofabrik.de/api/0.2/,geojson=false}}}}"
        
        st.write(f"Example format from docs: {example_format}")
        st.write("This format is likely for overpass-turbo, not for direct API calls")

with st.expander("How to use"):
    st.write("""
    1. Enter BBOX coordinates in one of these formats:
       - `98.041992,2.602864,98.052979,2.613839`
       - `[98.041992, 2.602864, 98.052979, 2.613839]`
       - `(98.041992, 2.602864, 98.052979, 2.613839)`
    
    2. Click "Find Overlapping Buildings"
    
    3. The app will:
       - Query Postpass for buildings in the area
       - Find overlapping building pairs
       - Display results in a table
       - Show overlapping areas on a map (if geometries are available)
       - Allow download as GeoJSON
    
    **Note:** The query uses `ST_Area(ST_Intersection(...)::geography)` to calculate overlap area in square meters.
    Only overlaps larger than 0.1 m² are returned to filter tiny overlaps.
    """)
