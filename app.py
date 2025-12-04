import streamlit as st
import requests
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely.geometry import box
import json

st.set_page_config(page_title="Building Overlap Detector", layout="wide")
st.title("🏠 Building Overlap Detector")

# Sidebar for inputs
with st.sidebar:
    st.header("🔧 Settings")
    
    # Bounding box input
    st.subheader("Enter Bounding Box (WGS84)")
    
    col1, col2 = st.columns(2)
    with col1:
        west = st.number_input("West (longitude)", value=-74.0060, format="%.6f")
        south = st.number_input("South (latitude)", value=40.7128, format="%.6f")
    with col2:
        east = st.number_input("East (longitude)", value=-73.9352, format="%.6f")
        north = st.number_input("North (latitude)", value=40.8105, format="%.6f")
    
    # Validate bbox
    if west >= east:
        st.error("West must be less than East")
    if south >= north:
        st.error("South must be less than North")
    
    # Buffer option
    buffer_km = st.slider("Buffer around bbox (km)", 0.0, 5.0, 0.0, 0.1)
    
    # Run button
    run_query = st.button("🔍 Find Overlapping Buildings", type="primary", use_container_width=True)

# Main content
if run_query:
    # Apply buffer if specified
    if buffer_km > 0:
        # Approximate conversion: 1 degree ≈ 111 km at equator
        buffer_deg = buffer_km / 111.0
        west_buff = west - buffer_deg
        east_buff = east + buffer_deg
        south_buff = south - buffer_deg
        north_buff = north + buffer_deg
        bbox = [west_buff, south_buff, east_buff, north_buff]
        st.info(f"Applied {buffer_km} km buffer to bounding box")
    else:
        bbox = [west, south, east, north]
    
    w, s, e, n = bbox
    
    # Display bbox info
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("West", f"{w:.6f}")
    with col2:
        st.metric("East", f"{e:.6f}")
    with col3:
        st.metric("South", f"{s:.6f}")
    with col4:
        st.metric("North", f"{n:.6f}")
    
    # Calculate area
    area_km2 = (e - w) * 111.0 * (n - s) * 111.0 * 0.8  # Rough approximation
    st.caption(f"Approximate area: {area_km2:.1f} km²")
    
    # Create a simple rectangle for visualization
    bbox_geometry = box(w, s, e, n)
    bbox_gdf = gpd.GeoDataFrame(
        {'id': [1], 'geometry': [bbox_geometry]},
        crs="EPSG:4326"
    )
    
    # Query Postpass for overlapping buildings
    with st.spinner("Querying Postpass for overlapping buildings..."):
        try:
            sql = f"""
            SELECT 
                a.osm_id AS building_a, 
                b.osm_id AS building_b, 
                ST_Area(ST_Intersection(a.geom, b.geom)) AS overlap_area_sqkm,
                ST_AsText(ST_Intersection(a.geom, b.geom)) AS geom_wkt
            FROM postpass_polygon AS a
            JOIN postpass_polygon AS b
              ON a.osm_id < b.osm_id
             AND a.tags ? 'building'
             AND b.tags ? 'building'
             AND a.geom && b.geom
             AND ST_Overlaps(a.geom, b.geom)
            WHERE a.geom && ST_MakeEnvelope({w},{s},{e},{n},4326)
            ORDER BY overlap_area_sqkm DESC
            LIMIT 1000
            """
            
            response = requests.post(
                "https://postpass.geofabrik.de/api/0.2/interpreter",
                data={"data": sql, "options[geojson]": "false"},
                timeout=120
            )
            response.raise_for_status()
            data = response.json()
            
            st.success(f"Query completed successfully!")
            
        except requests.exceptions.Timeout:
            st.error("Query timed out. Try a smaller area or remove the buffer.")
            st.stop()
        except Exception as ex:
            st.error(f"Postpass query failed: {ex}")
            st.stop()

    if len(data) == 0:
        st.warning("No overlapping buildings found in this area.")
        
        # Still show the map with just the bbox
        m = folium.Map(location=[(s+n)/2, (w+e)/2], zoom_start=14)
        folium.GeoJson(
            bbox_gdf,
            style_function=lambda x: {
                'fillColor': 'blue',
                'color': 'blue',
                'weight': 3,
                'fillOpacity': 0.1
            },
            tooltip="Search Area"
        ).add_to(m)
        
        st.subheader("📍 Search Area")
        st_folium(m, width=800, height=500)
        
    else:
        st.success(f"Found {len(data)} overlapping building pairs!")
        
        # Convert WKT to GeoDataFrame
        gdf = gpd.GeoDataFrame(
            data, 
            geometry=gpd.GeoSeries.from_wkt([f["geom_wkt"] for f in data])
        )
        
        # Convert area from degrees² to km² (rough approximation)
        gdf['overlap_area_sqkm'] = gdf['overlap_area_sqkm'] * 111.0 * 111.0 * 0.8
        
        # Calculate total overlap area
        total_overlap_area = gdf['overlap_area_sqkm'].sum()
        
        # Display metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Overlap Pairs", len(data))
        with col2:
            st.metric("Largest Overlap", f"{gdf['overlap_area_sqkm'].max():.4f} km²")
        with col3:
            st.metric("Total Overlap Area", f"{total_overlap_area:.4f} km²")
        
        # Map preview
        st.subheader("🗺️ Map Preview")
        
        m = folium.Map(location=[(s+n)/2, (w+e)/2], zoom_start=15)
        
        # Add search area boundary
        folium.GeoJson(
            bbox_gdf,
            style_function=lambda x: {
                'fillColor': 'blue',
                'color': 'blue',
                'weight': 3,
                'fillOpacity': 0.05,
                'dashArray': '5, 5'
            },
            name="Search Area"
        ).add_to(m)
        
        # Add overlapping buildings with color based on overlap area
        def style_function(feature):
            area = feature['properties']['overlap_area_sqkm']
            if area > 0.001:  # > 1000 m²
                return {'fillColor': 'red', 'color': 'red', 'weight': 2, 'fillOpacity': 0.7}
            elif area > 0.0001:  # > 100 m²
                return {'fillColor': 'orange', 'color': 'orange', 'weight': 2, 'fillOpacity': 0.7}
            else:
                return {'fillColor': 'yellow', 'color': 'yellow', 'weight': 2, 'fillOpacity': 0.7}
        
        folium.GeoJson(
            gdf,
            style_function=style_function,
            tooltip=folium.GeoJsonTooltip(
                fields=['building_a', 'building_b', 'overlap_area_sqkm'],
                aliases=['Building A:', 'Building B:', 'Overlap Area (km²):'],
                localize=True,
                style="background-color: white;"
            ),
            name="Overlapping Buildings"
        ).add_to(m)
        
        folium.LayerControl().add_to(m)
        
        # Display map
        map_col1, map_col2 = st.columns([3, 1])
        with map_col1:
            st_folium(m, width=800, height=600)
        
        with map_col2:
            st.caption("**Color Legend**")
            st.markdown("""
            <div style="background-color: red; padding: 5px; margin: 2px; border-radius: 3px; color: white;">
            Large overlap (>1000 m²)
            </div>
            <div style="background-color: orange; padding: 5px; margin: 2px; border-radius: 3px; color: black;">
            Medium overlap (100-1000 m²)
            </div>
            <div style="background-color: yellow; padding: 5px; margin: 2px; border-radius: 3px; color: black;">
            Small overlap (<100 m²)
            </div>
            """, unsafe_allow_html=True)
        
        # Data table
        st.subheader("📊 Overlap Data")
        
        # Show summary table
        summary_df = gdf[['building_a', 'building_b', 'overlap_area_sqkm']].copy()
        summary_df['overlap_area_m2'] = (summary_df['overlap_area_sqkm'] * 1000000).round(2)
        summary_df['overlap_area_sqkm'] = summary_df['overlap_area_sqkm'].round(6)
        summary_df = summary_df.sort_values('overlap_area_m2', ascending=False)
        
        st.dataframe(
            summary_df,
            column_config={
                "building_a": "OSM ID A",
                "building_b": "OSM ID B",
                "overlap_area_sqkm": st.column_config.NumberColumn(
                    "Area (km²)",
                    format="%.6f"
                ),
                "overlap_area_m2": st.column_config.NumberColumn(
                    "Area (m²)",
                    format="%.2f"
                )
            },
            use_container_width=True,
            height=400
        )
        
        # Download buttons
        st.subheader("💾 Download Data")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Download overlaps as GeoJSON
            geojson_str = gdf.to_json()
            st.download_button(
                label="Download Overlaps (GeoJSON)",
                data=geojson_str,
                file_name=f"overlapping_buildings_{w:.4f}_{s:.4f}_{e:.4f}_{n:.4f}.geojson",
                mime="application/geo+json",
                use_container_width=True
            )
        
        with col2:
            # Download as CSV (geometry as WKT)
            csv_data = gdf.copy()
            csv_data['geometry_wkt'] = csv_data['geometry'].apply(lambda x: x.wkt)
            csv_str = csv_data[['building_a', 'building_b', 'overlap_area_sqkm', 'geometry_wkt']].to_csv(index=False)
            st.download_button(
                label="Download Overlaps (CSV)",
                data=csv_str,
                file_name=f"overlapping_buildings_{w:.4f}_{s:.4f}_{e:.4f}_{n:.4f}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        # Also download the search area
        st.download_button(
            label="Download Search Area (GeoJSON)",
            data=bbox_gdf.to_json(),
            file_name=f"search_area_{w:.4f}_{s:.4f}_{e:.4f}_{n:.4f}.geojson",
            mime="application/geo+json",
            use_container_width=True
        )

# Instructions in main area when not running
else:
    st.markdown("""
    ## 📍 How to Use
    
    1. **Enter coordinates** in the sidebar (WGS84 format)
    2. **Adjust buffer** if you want to search slightly outside the box
    3. **Click the button** to find overlapping buildings
    
    ### 🔍 Tips:
    - Start with a small area (1-2 km²) for faster results
    - Larger areas may timeout (> 10 km²)
    - Use the buffer to include buildings near the edges
    
    ### 📋 Default coordinates show Manhattan, NYC
    - West: -74.0060 (Hudson River)
    - East: -73.9352 (East River)
    - South: 40.7128 (Financial District)
    - North: 40.8105 (Central Park North)
    """)
