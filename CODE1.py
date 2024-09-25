import ee
import geemap
import os
import sys
import osmnx as ox

# Initialize Earth Engine
ee.Initialize()

# User inputs
city_name = 'Riyadh'  # Replace with your desired city name
start_date = '2020-01-01'
end_date = '2020-01-10'
max_cloud_percentage = 5  # Maximum allowed cloud cover percentage
output_folder = 'output_images'  # Folder to save images

# Create output directory if it doesn't exist
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Get the boundary of the city using OSMnx
try:
    city_boundary = ox.geocode_to_gdf(city_name)
    print(f"City found: {city_name}")
    # Convert to GeoJSON
    city_geojson = city_boundary['geometry'].iloc[0].__geo_interface__
    # Convert to Earth Engine Geometry
    roi = ee.Geometry(city_geojson)
except Exception as e:
    print(f"Error obtaining city boundary: {e}")
    sys.exit(1)

# Simplify the geometry if necessary to reduce complexity
roi = roi.simplify(maxError=100)

# Transform the ROI to the same CRS
roi_proj = roi.transform('EPSG:3857', maxError=100)

# Subdivide the ROI into 1km x 1km grid cells
grid = geemap.fishnet(
    data=roi_proj,        # Transformed ROI
    dx=1000,              # Cell width in meters (1 km)
    dy=1000,              # Cell height in meters (1 km)
    crs='EPSG:3857'       # Coordinate reference system
)


grid_size = grid.size().getInfo()
print(f"Total grid cells created: {grid_size}")

# Prepare the Sentinel-2 image collection
collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
              .filterDate(start_date, end_date)
              .filterBounds(roi)
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_cloud_percentage))
              .select(['B8', 'B4', 'B3', 'B2']))

collection_size = collection.size().getInfo()
print(f"Total images in collection: {collection_size}")

# Function to process each grid cell
def process_cell(cell_feature):
    cell_geom = cell_feature.geometry()
    # Filter the collection to the grid cell
    cell_collection = collection.filterBounds(cell_geom)
    # Get the least cloudy image
    image = cell_collection.sort('CLOUDY_PIXEL_PERCENTAGE').first()
    if image:
        # Crop the image to the cell geometry
        image = image.clip(cell_geom)
        # Define the output filename
        cell_id = cell_feature.get('system:index').getInfo()
        filename = f'sentinel_{cell_id}.tif'
        out_path = os.path.join(output_folder, filename)
        # Export the image
        try:
            geemap.ee_export_image(
                ee_object=image,
                filename=out_path,
                scale=10,  # Sentinel-2 spatial resolution is 10 meters
                region=cell_geom,
                file_per_band=False,
                maxPixels=1e9       # Adjust as needed
            )
            print(f"Image saved: {filename}")
        except Exception as e:
            print(f"An error occurred while exporting {filename}: {e}")
    else:
        print(f'No suitable image found for cell {cell_id}.')

# Iterate over the grid cells
grid_list = grid.toList(grid.size())

# For testing purposes, you may limit the number of cells processed
# num_cells_to_process = 10
# grid_size = min(grid.size().getInfo(), num_cells_to_process)

for i in range(grid_size):
    cell_feature = ee.Feature(grid_list.get(i))
    process_cell(cell_feature)
