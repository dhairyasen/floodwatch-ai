import ee
import geemap
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import json
import os
import warnings
warnings.filterwarnings('ignore')

from config import *

class FloodAnalyzer:
    def __init__(self):
        self.backend_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_dir = os.path.dirname(self.backend_dir)
        self.outputs_dir = os.path.join(self.project_dir, 'outputs')
        os.makedirs(self.outputs_dir, exist_ok=True)
    
    def get_coordinates(self, location, lat=None, lon=None):
        # If coordinates directly provided (from Nominatim), use them
        if lat is not None and lon is not None:
            return float(lat), float(lon), location
        location_lower = location.lower()
        if location_lower in CITY_COORDINATES:
            coords = CITY_COORDINATES[location_lower]
            return coords['lat'], coords['lon'], coords['name']
        else:
            try:
                parts = location.split(',')
                lat = float(parts[0].strip())
                lon = float(parts[1].strip())
                return lat, lon, f"{lat}, {lon}"
            except:
                raise ValueError("Invalid location")
    
    def fetch_satellite_data(self, lat, lon, start_date, end_date):
        point = ee.Geometry.Point([lon, lat])
        roi = point.buffer(BUFFER_DISTANCE)
        
        # CRITICAL FIX: Convert DD-MM-YYYY to YYYY-MM-DD format for GEE
        try:
            # Try parsing as DD-MM-YYYY first (frontend format)
            start_dt = datetime.strptime(start_date, '%d-%m-%Y')
            start_date_formatted = start_dt.strftime('%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%d-%m-%Y')
            end_date_formatted = end_dt.strftime('%Y-%m-%d')
        except ValueError:
            # Already in YYYY-MM-DD format
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            start_date_formatted = start_date
            end_date_formatted = end_date
        
        if start_dt >= datetime(2022, 1, 25):
            collection_name = 'COPERNICUS/S2_SR_HARMONIZED'
        else:
            collection_name = 'COPERNICUS/S2_SR'
        
        try:
            dataset = ee.ImageCollection(collection_name) \
                .filterDate(start_date_formatted, end_date_formatted) \
                .filterBounds(roi) \
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', CLOUD_THRESHOLD))
            
            count = dataset.size().getInfo()
            if count == 0:
                raise Exception(f"No clear satellite images found for {start_date_formatted} to {end_date_formatted}. Try different dates or increase cloud threshold in config.py")
            
            image = dataset.median().clip(roi)
            return image, roi, count
        except Exception as e:
            if 'HARMONIZED' in collection_name:
                print(f"Harmonized dataset failed, trying regular SR...")
                dataset = ee.ImageCollection('COPERNICUS/S2_SR') \
                    .filterDate(start_date_formatted, end_date_formatted) \
                    .filterBounds(roi) \
                    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', CLOUD_THRESHOLD))
                
                count = dataset.size().getInfo()
                if count == 0:
                    raise Exception(f"No satellite images found. Try: 1) Earlier dates, 2) Different months, 3) Increase CLOUD_THRESHOLD in config.py")
                
                image = dataset.median().clip(roi)
                return image, roi, count
            else:
                raise e
    def calculate_water_indices(self, image):
        ndwi = image.normalizedDifference(['B3', 'B8']).rename('NDWI')
        mndwi = image.normalizedDifference(['B3', 'B11']).rename('MNDWI')
        return image.addBands([ndwi, mndwi])
    
    def detect_water(self, image_with_indices):
        ndwi = image_with_indices.select('NDWI')
        mndwi = image_with_indices.select('MNDWI')
        water = ndwi.gt(NDWI_THRESHOLD).Or(mndwi.gt(MNDWI_THRESHOLD))
        return water.selfMask()
    
    def create_land_only_mask(self, roi):
        """
        Balanced land mask - excludes permanent water bodies using 30% threshold
        30% allows detection of seasonal flooding while excluding permanent lakes/rivers
        """
        try:
            print("  - Loading permanent water database (BALANCED MODE)...")
            gsw = ee.Image('JRC/GSW1_4/GlobalSurfaceWater')
            # Water occurrence >30% = regular water bodies (lakes, major rivers)
            # This is balanced - strict enough to exclude permanent water but loose enough for flood detection
            permanent_water = gsw.select('occurrence').gt(30)
            
            print("  - Loading elevation data...")
            dem = ee.Image('USGS/SRTMGL1_003')
            # Elevation >0m = above sea level
            land_elevation = dem.gt(0)
            
            print("  - Combining filters (BALANCED)...")
            # LAND = NOT permanent water AND above sea level
            land_mask = permanent_water.Not().And(land_elevation)
            
            return land_mask.clip(roi)
            
        except Exception as e:
            print(f"  Warning: Land mask creation failed ({e})")
            print("  - Using elevation-only fallback...")
            try:
                dem = ee.Image('USGS/SRTMGL1_003')
                return dem.gt(0).clip(roi)
            except:
                print("  Warning: All masks failed, using full area")
                return ee.Image.constant(1).clip(roi)
    
    def calculate_area(self, image, roi):
        try:
            area = image.multiply(ee.Image.pixelArea()).reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=roi,
                scale=SCALE,
                maxPixels=1e10
            )
            area_dict = area.getInfo()
            if not area_dict:
                return 0.0
            # Get first available key instead of hardcoding 'NDWI'
            value = list(area_dict.values())[0]
            area_km2 = (value or 0) / 1e6
            return area_km2
        except Exception as e:
            print(f"Warning: Area calculation failed: {e}")
            return 0.0
    
    def create_map(self, lat, lon, location_name, water_before_land, water_after_land, new_flood_layer, roi):
        """Create flood map with 3 toggleable layers: Water Before, New Flooded, and Total Difference"""
        map_path = os.path.join(self.outputs_dir, 'flood_map.html')
        
        # Delete old map to prevent stale cache
        if os.path.exists(map_path):
            os.remove(map_path)
        
        try:
            print("  - Creating multi-layer flood map...")
            import folium
            from folium import plugins
            
            # Create folium map
            m = folium.Map(
                location=[lat, lon], 
                zoom_start=11,
                tiles='OpenStreetMap',
                control_scale=True
            )
            
            # Calculate the area difference (all changes - both increases and decreases)
            print("  - Calculating all three layers...")
            # Water that decreased (was there before, not there after)
            water_decreased = water_before_land.And(water_after_land.Not())
            # Water that increased (new flooding)
            water_increased = new_flood_layer
            # Total difference = both increases and decreases
            area_difference = water_decreased.Or(water_increased)
            
            # Get Earth Engine tile URLs for all three layers
            print("  - Generating Earth Engine tiles for all layers...")
            try:
                # Layer 1: Water Before (CYAN) - increased opacity
                before_vis = {'palette': ['#00FFFF'], 'opacity': 0.85}
                before_map_id = water_before_land.getMapId(before_vis)
                before_tile_url = before_map_id['tile_fetcher'].url_format
                
                # Layer 2: New Flooded Areas (RED) - increased opacity
                flood_vis = {'palette': ['#FF0000'], 'opacity': 0.9}
                flood_map_id = new_flood_layer.getMapId(flood_vis)
                flood_tile_url = flood_map_id['tile_fetcher'].url_format
                
                # Layer 3: Area Difference (YELLOW) - increased opacity
                diff_vis = {'palette': ['#FFFF00'], 'opacity': 0.85}
                diff_map_id = area_difference.getMapId(diff_vis)
                diff_tile_url = diff_map_id['tile_fetcher'].url_format
                
                print("  - Adding tile layers to map...")
                
                # Add Water Before layer (CYAN) - increased opacity
                folium.TileLayer(
                    tiles=before_tile_url,
                    attr='Google Earth Engine',
                    name='Water Before (CYAN)',
                    overlay=True,
                    control=True,
                    opacity=0.85,
                    show=False  # OFF by default
                ).add_to(m)
                
                # Add New Flooded Areas layer (RED) - increased opacity
                folium.TileLayer(
                    tiles=flood_tile_url,
                    attr='Google Earth Engine',
                    name='New Flooded Areas (RED)',
                    overlay=True,
                    control=True,
                    opacity=0.9,
                    show=True  # ON by default
                ).add_to(m)
                
                # Add Area Difference layer (YELLOW) - increased opacity
                folium.TileLayer(
                    tiles=diff_tile_url,
                    attr='Google Earth Engine',
                    name='Area Difference (YELLOW)',
                    overlay=True,
                    control=True,
                    opacity=0.85,
                    show=False  # OFF by default
                ).add_to(m)
                
                print("  - All layers added successfully!")
                
            except Exception as tile_error:
                print(f"  Warning: Could not create tile layers: {tile_error}")
                print("  - Map will display without flood layers...")
            
            # Add center marker
            folium.Marker(
                [lat, lon],
                popup=folium.Popup(f'<b>{location_name}</b><br>Flood Analysis Center', max_width=200),
                tooltip='Analysis Center',
                icon=folium.Icon(color='blue', icon='water', prefix='fa')
            ).add_to(m)
            
            # Add a circle showing the analysis area
            folium.Circle(
                location=[lat, lon],
                radius=50000,  # 50km buffer
                color='blue',
                fill=False,
                weight=2,
                opacity=0.5,
                popup='Analysis Area (50km radius)'
            ).add_to(m)
            
            # Add fullscreen button
            plugins.Fullscreen(
                position='topright',
                title='Fullscreen',
                title_cancel='Exit Fullscreen',
                force_separate_button=True
            ).add_to(m)
            
            # Add measure control
            plugins.MeasureControl(
                position='topleft',
                primary_length_unit='kilometers',
                secondary_length_unit='meters',
                primary_area_unit='sqkilometers'
            ).add_to(m)
            
            # Add comprehensive legend
            legend_html = '''
            <div style="position: fixed; 
                        bottom: 50px; right: 50px; 
                        width: 220px; 
                        background: white; 
                        z-index: 1000;
                        border: 2px solid #0066cc;
                        border-radius: 8px;
                        padding: 15px;
                        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
                        font-family: Arial, sans-serif;">
                <h4 style="margin: 0 0 12px 0; 
                           color: #1e293b; 
                           font-size: 16px;
                           border-bottom: 2px solid #e2e8f0;
                           padding-bottom: 8px;">
                     Flood Detection Layers
                </h4>
                <div style="margin: 10px 0;">
                    <div style="display: flex; align-items: center; margin: 10px 0;">
                        <div style="width: 24px; 
                                    height: 24px; 
                                    background: #00FFFF; 
                                    border-radius: 3px;
                                    margin-right: 10px;
                                    opacity: 0.6;
                                    border: 1px solid #00CCCC;"></div>
                        <div>
                            <div style="font-size: 13px; font-weight: 600;">Water Before</div>
                            <div style="font-size: 10px; color: #64748b;">Baseline water</div>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; margin: 10px 0;">
                        <div style="width: 24px; 
                                    height: 24px; 
                                    background: #FF0000; 
                                    border-radius: 3px;
                                    margin-right: 10px;
                                    opacity: 0.7;
                                    border: 1px solid #CC0000;"></div>
                        <div>
                            <div style="font-size: 13px; font-weight: 600;">New Flooded</div>
                            <div style="font-size: 10px; color: #64748b;">Newly flooded areas</div>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; margin: 10px 0;">
                        <div style="width: 24px; 
                                    height: 24px; 
                                    background: #FFFF00; 
                                    border-radius: 3px;
                                    margin-right: 10px;
                                    opacity: 0.65;
                                    border: 1px solid #CCCC00;"></div>
                        <div>
                            <div style="font-size: 13px; font-weight: 600;">Area Difference</div>
                            <div style="font-size: 10px; color: #64748b;">All water changes</div>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; margin: 10px 0;">
                        <div style="width: 24px; 
                                    height: 24px; 
                                    background: #0066cc; 
                                    border: 2px solid #0066cc;
                                    border-radius: 50%;
                                    margin-right: 10px;"></div>
                        <div>
                            <div style="font-size: 13px;">Analysis Center</div>
                        </div>
                    </div>
                </div>
                <hr style="margin: 12px 0; border: none; border-top: 1px solid #e2e8f0;">
                <p style="margin: 8px 0 0 0; 
                          font-size: 10px; 
                          color: #64748b;
                          line-height: 1.5;">
                    📍 ''' + location_name + '''<br>
                    🛰️ Sentinel-2 (10m resolution)<br>
                    ⚡ Excludes permanent water<br>
                    💡 Toggle layers using top-right controls
                </p>
            </div>
            '''
            m.get_root().html.add_child(folium.Element(legend_html))
            
            # Add layer control for toggling layers
            folium.LayerControl(position='topright', collapsed=False).add_to(m)
            
            # Save map
            print("  - Saving map...")
            m.save(map_path)
            print("  ✓ Map created successfully!")
            return map_path
            
        except Exception as e:
            print(f"  ERROR creating map: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Fallback: basic map with marker only
            print("  - Creating fallback map...")
            try:
                import folium
                m = folium.Map(location=[lat, lon], zoom_start=10)
                folium.Marker(
                    [lat, lon],
                    popup=f'<b>{location_name}</b><br>Flood Analysis<br>See charts for results',
                    icon=folium.Icon(color='red', icon='warning', prefix='fa')
                ).add_to(m)
                
                # Simple warning overlay
                warning_html = '''
                <div style="position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
                            background: white; padding: 30px; border-radius: 12px;
                            box-shadow: 0 8px 16px rgba(0,0,0,0.2); z-index: 2000;
                            text-align: center; max-width: 400px;">
                    <h2 style="color: #ef4444; margin: 0 0 15px 0;">⚠️ Map Unavailable</h2>
                    <p style="color: #64748b; margin: 0 0 20px 0;">
                        The detailed flood map could not be generated.<br>
                        Please refer to the charts and statistics below for analysis results.
                    </p>
                    <button onclick="this.parentElement.style.display='none'" 
                            style="background: #3b82f6; color: white; border: none;
                                   padding: 10px 24px; border-radius: 6px; cursor: pointer;
                                   font-size: 14px; font-weight: 600;">
                        View Results Below
                    </button>
                </div>
                '''
                m.get_root().html.add_child(folium.Element(warning_html))
                
                m.save(map_path)
                print("  ✓ Fallback map created")
                return map_path
            except:
                print("  ✗ All map creation methods failed")
                return None
    
    def create_visualizations(self, results):
        sns.set_style("whitegrid")
        plt.rcParams['font.family'] = 'sans-serif'
        
        # Chart 1: Bar Chart
        fig, ax = plt.subplots(figsize=(10, 6))
        
        categories = ['Water Before', 'Water After', 'New Flooded']
        values = [results['water_before'], results['water_after'], results['new_flooded_area']]
        colors = ['#3b82f6', '#ef4444', '#f59e0b']
        
        bars = ax.bar(categories, values, color=colors, alpha=0.8, edgecolor='black', linewidth=1.5)
        
        ax.set_ylabel('Area (km²)', fontsize=12, fontweight='bold')
        ax.set_title(f"Water Coverage Analysis - {results['location_name']}", 
                    fontsize=14, fontweight='bold', pad=20)
        ax.grid(axis='y', alpha=0.3)
        
        for bar, val in zip(bars, values):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height, f'{val:.2f} km²',
                   ha='center', va='bottom', fontweight='bold', fontsize=11)
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.outputs_dir, 'water_coverage.png'), dpi=300, bbox_inches='tight')
        plt.close()
        
        # Chart 2: Pie Chart - handles all scenarios
        fig, ax = plt.subplots(figsize=(8, 8))
        
        change_pct = results['water_coverage_change']
        new_flood = results['new_flooded_area']
        
        if new_flood > 1.0:  # Significant flooding
            existing = results['water_before']
            sizes = [new_flood, existing]
            labels = [f'New Flooded\n({new_flood:.1f} km²)', 
                     f'Baseline Water\n({existing:.1f} km²)']
            colors_pie = ['#ef4444', '#3b82f6']
            explode = (0.1, 0)
            
            wedges, texts, autotexts = ax.pie(sizes, explode=explode, labels=labels, 
                   colors=colors_pie, autopct='%1.1f%%', shadow=True, startangle=90,
                   textprops={'fontsize': 10, 'weight': 'bold'})
            
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontsize(11)
                autotext.set_weight('bold')
            
            ax.set_title('Flood Severity Breakdown', fontsize=14, fontweight='bold', pad=20)
            
        elif change_pct < -5:  # Water DECREASED
            ax.text(0.5, 0.5, 
                   f'Water Level DECREASED\n\n'
                   f'Reduction: {abs(change_pct):.0f}%\n\n'
                   f'(Drying trend - No flooding)', 
                   ha='center', va='center', fontsize=13, 
                   transform=ax.transAxes,
                   bbox=dict(boxstyle='round', facecolor='#d4edda', 
                            alpha=0.8, edgecolor='#28a745', linewidth=3))
            ax.set_title('Water Status: Improving', fontsize=14, fontweight='bold', pad=20)
            
        else:  # Minimal change
            ax.text(0.5, 0.5, 
                   f'MINIMAL CHANGE\n\n'
                   f'Change: {change_pct:+.1f}%\n\n'
                   f'(No significant flooding)', 
                   ha='center', va='center', fontsize=13, 
                   transform=ax.transAxes,
                   bbox=dict(boxstyle='round', facecolor='#d1ecf1', 
                            alpha=0.8, edgecolor='#17a2b8', linewidth=3))
            ax.set_title('Water Status: Stable', fontsize=14, fontweight='bold', pad=20)
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.outputs_dir, 'water_composition.png'), dpi=300, bbox_inches='tight')
        plt.close()
        
        # Chart 3: Summary
        fig, ax = plt.subplots(figsize=(10, 7))
        ax.axis('off')
        
        if new_flood > 100:
            severity = "CRITICAL"
        elif new_flood > 50:
            severity = "HIGH"
        elif new_flood > 10:
            severity = "MEDIUM"
        elif new_flood > 1.0:
            severity = "LOW"
        elif change_pct < -5:
            severity = "WATER RECEDED"
        else:
            severity = "MINIMAL CHANGE"
        
        summary = f"""
FLOOD ANALYSIS REPORT

LOCATION: {results['location_name']}
Coordinates: {results['coordinates']['lat']:.4f} N, {results['coordinates']['lon']:.4f} E

PERIOD: {results['start_date']} to {results['end_date']}

METRICS (Land Areas Only)
Study Area: {results['study_area']:.1f} km²
Water Before: {results['water_before']:.2f} km² (CYAN)
Water After: {results['water_after']:.2f} km²

NEW FLOODED: {results['new_flooded_area']:.2f} km² (RED)
Change: {results['water_coverage_change']:+.1f}%

Severity: {severity}

SOURCE: Sentinel-2 | Images: {results['image_count']} | Resolution: 10m

NOTE: Ocean/sea excluded from analysis

Generated: {results['timestamp'][:10]}
        """
        
        ax.text(0.05, 0.95, summary, transform=ax.transAxes, fontsize=10,
               verticalalignment='top', fontfamily='monospace',
               bbox=dict(boxstyle='round', facecolor='#e6f7ff', alpha=0.8, edgecolor='#0066cc', linewidth=2))
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.outputs_dir, 'summary.png'), dpi=300, bbox_inches='tight')
        plt.close()
    
    def analyze(self, location, before_start_date, before_end_date, after_start_date, after_end_date, lat=None, lon=None):
        try:
            print(f"\n{'='*60}")
            print(f"FLOOD ANALYSIS: {location}")
            print(f"{'='*60}\n")
            
            lat, lon, location_name = self.get_coordinates(location, lat, lon)
            study_area = (BUFFER_DISTANCE * 2 / 1000) ** 2
            
            print(f"Location: {lat} N, {lon} E")
            print(f"Study area: {study_area:.1f} km²\n")
            
            print(f"Fetching baseline ({before_start_date} to {before_end_date})...")
            image_before, roi, count_before = self.fetch_satellite_data(lat, lon, before_start_date, before_end_date)
            print(f"   Found {count_before} images")
            
            print(f"\nFetching current ({after_start_date} to {after_end_date})...")
            image_after, roi, count_after = self.fetch_satellite_data(lat, lon, after_start_date, after_end_date)
            print(f"   Found {count_after} images")
            
            print(f"\nAnalyzing water...")
            water_before_all = self.detect_water(self.calculate_water_indices(image_before))
            water_after_all = self.detect_water(self.calculate_water_indices(image_after))
            
            print(f"\nCreating land mask (excluding ocean and permanent water)...")
            land_mask = self.create_land_only_mask(roi)
            
            # CRITICAL: Apply land mask first
            water_before_land = water_before_all.updateMask(land_mask)
            water_after_land = water_after_all.updateMask(land_mask)
            
            # BULLETPROOF APPROACH: Also exclude areas that had water in "before" period
            # This catches any water bodies missed by the permanent water database
            print(f"\nApplying triple-layer filtering...")
            print(f"  Layer 1: Permanent water database (>30% occurrence)")
            print(f"  Layer 2: Elevation (exclude ocean)")
            print(f"  Layer 3: Exclude water detected in 'before' period")
            
            # Calculate new flooding: water in "after" that was NOT in "before"
            new_flood_layer = water_after_land.And(water_before_land.Not())
            
            # Calculate areas
            water_before_area = self.calculate_area(water_before_land, roi)
            water_after_area = self.calculate_area(water_after_land, roi)
            new_flooded_area_actual = self.calculate_area(new_flood_layer, roi)
            
            print(f"   Before: {water_before_area:.2f} km²")
            print(f"   After: {water_after_area:.2f} km²")
            print(f"   NEW FLOODED (actual): {new_flooded_area_actual:.2f} km²")
            
            # FALLBACK: If actual calculation returns 0 but water increased, use simple math
            if new_flooded_area_actual < 0.01 and water_after_area > water_before_area:
                print(f"   WARNING: Layer calculation returned 0, using simple subtraction")
                new_flooded_area = max(0, water_after_area - water_before_area)
            else:
                new_flooded_area = new_flooded_area_actual
            
            water_coverage_change = ((new_flooded_area) / water_before_area * 100) if water_before_area > 0 else 0
            
            print(f"\n{'='*60}")
            print(f"RESULT: {new_flooded_area:.2f} km² new flooding")
            print(f"Change: {water_coverage_change:+.1f}%")
            print(f"{'='*60}\n")
            
            print("Generating map...")
            self.create_map(lat, lon, location_name, water_before_land, water_after_land, new_flood_layer, roi)
            
            results = {
                'location': location,
                'location_name': location_name,
                'coordinates': {'lat': lat, 'lon': lon},
                'start_date': after_start_date,
                'end_date': after_end_date,
                'study_area': round(study_area, 2),
                'water_before': round(water_before_area, 2),
                'water_after': round(water_after_area, 2),
                'new_flooded_area': round(new_flooded_area, 2),
                'water_coverage_change': round(water_coverage_change, 1),
                'image_count': count_before + count_after,
                'timestamp': datetime.now().isoformat()
            }
            
            print("Creating charts...")
            self.create_visualizations(results)
            
            with open(os.path.join(self.outputs_dir, 'results.json'), 'w') as f:
                json.dump(results, f, indent=2)
            
            print("Complete!\n")
            return results
            
        except Exception as e:
            print(f"\nANALYIS FAILED: {str(e)}")
            import traceback
            traceback.print_exc()
            raise e
        
        