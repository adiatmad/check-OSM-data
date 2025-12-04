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
            # Proper Overpass/Postpass query format
            # First, let's test with a simpler query to check if Postpass works
            # We'll get buildings first, then find overlaps
            
            # Query 1: Get all buildings in the bbox
            query = f"""
            [out:json][timeout:90];
            (
              way["building"]({south},{west},{north},{east});
              relation["building"]({south},{west},{north},{east});
            );
            out body;
            >;
            out skel qt;
            """
            
            st.info(f"Querying BBOX: {south},{west},{north},{east}")
            
            response = requests.post(
                "https://postpass.geofabrik.de/api/0.2/interpreter",
                data={"data": query},
                timeout=120
            )
            
            # Check response
            st.write(f"Response status: {response.status_code}")
            
            if response.status_code != 200:
                st.error(f"API Error {response.status_code}: {response.text[:200]}")
                st.stop()
                
            response.raise_for_status()
            
            # Parse the response
            result = response.json()
            
            st.write(f"Found {len(result.get('elements', []))} building elements")
            
            # Debug: Show first few elements
            if result.get('elements'):
                st.write("First element sample:")
                st.json(result['elements'][0])
            
        except requests.exceptions.RequestException as e:
            st.error(f"Network error: {e}")
            if hasattr(e.response, 'text'):
                st.write(f"Error details: {e.response.text[:500]}")
            st.stop()
        except ValueError as e:
            st.error(f"Invalid JSON response: {e}")
            if 'response' in locals():
                st.write(f"Raw response: {response.text[:500]}")
            st.stop()
        except Exception as ex:
            st.error(f"Postpass query failed: {ex}")
            import traceback
            st.write(traceback.format_exc())
            st.stop()
    
    # Process buildings and find overlaps (simplified approach)
    if not result.get('elements'):
        st.warning("No buildings found in this BBOX.")
        st.info(f"BBOX used: south={south}, west={west}, north={north}, east={east}")
    else:
        try:
            # For now, let's just display the buildings on a map
            # In a real implementation, we would need to:
            # 1. Parse building geometries from OSM elements
            # 2. Use a spatial library to find overlaps
            
            st.warning("Note: Full overlap detection requires complex geometry processing.")
            st.info(f"Found {len(result['elements'])} building elements. Displaying on map...")
            
            # Create a simple map with building markers
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
            
            # Add building markers (simplified - using node positions)
            building_count = 0
            for element in result['elements']:
                if element.get('type') == 'node':
                    lat = element.get('lat')
                    lon = element.get('lon')
                    if lat and lon:
                        folium.CircleMarker(
                            location=[lat, lon],
                            radius=3,
                            color='red',
                            fill=True,
                            fill_color='red',
                            tooltip=f"Building Node: {element.get('id')}"
                        ).add_to(m)
                        building_count += 1
                elif element.get('type') == 'way' and element.get('center'):
                    # Some ways have center coordinates
                    lat = element.get('center', {}).get('lat')
                    lon = element.get('center', {}).get('lon')
                    if lat and lon:
                        folium.CircleMarker(
                            location=[lat, lon],
                            radius=5,
                            color='green',
                            fill=True,
                            fill_color='green',
                            tooltip=f"Building Way: {element.get('id')}"
                        ).add_to(m)
                        building_count += 1
            
            # Display map
            st.subheader(f"Found {building_count} building locations")
            st_folium(m, width=700, height=500)
            
            # Show data table
            st.subheader("Building Elements (sample)")
            display_data = []
            for element in result['elements'][:20]:  # Show first 20
                display_data.append({
                    'id': element.get('id'),
                    'type': element.get('type'),
                    'tags': str(element.get('tags', {}))
                })
            
            if display_data:
                st.dataframe(display_data)
            
        except Exception as e:
            st.error(f"Error processing data: {e}")
            import traceback
            st.write(traceback.format_exc())

# Alternative approach using a simpler query
with st.expander("Alternative: Direct overlap query (may not work on Postpass)"):
    st.write("""
    **Note:** Postpass may not support complex spatial queries like ST_Overlaps.
    For full overlap detection, you would need to:
    
    1. Download all buildings in the area
    2. Use local Python libraries (shapely, geopandas) to find overlaps
    3. Process the overlaps locally
    
    This requires more advanced processing but gives more accurate results.
    """)
    
    if st.button("Try alternative approach (local processing)"):
        st.info("This would require downloading full building geometries and processing locally.")

with st.expander("How to use"):
    st.write("""
    1. Enter BBOX coordinates in one of these formats:
       - `98.041992,2.602864,98.052979,2.613839`
       - `[98.041992, 2.602864, 98.052979, 2.613839]`
       - `(98.041992, 2.602864, 98.052979, 2.613839)`
    
    2. Click "Find Overlapping Buildings"
    
    3. The map will show:
       - Blue rectangle: Your search area
       - Red/green dots: Building locations
    
    **Limitations:**
    - This shows building locations but not actual polygon overlaps
    - For full overlap detection, local processing is needed
    - Large areas may timeout
    """)
