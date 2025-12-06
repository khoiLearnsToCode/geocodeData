import requests
import pandas as pd
import numpy as np
import time
import sqlite3
import polyline

# ==========================================
# 1. LOAD & CLEAN DATA
# ==========================================
def load_and_clean_data():
    print("Loading data...")
    # Load files
    df_eateries = pd.read_csv('dalat_eateries.csv')
    df_pois = pd.read_csv('dalat_pois.csv')

    # Standardize columns to merge them easily
    df_eateries = df_eateries[['ID', 'Lat', 'Lon']].copy()
    df_pois = df_pois[['ID', 'Lat', 'Lon']].copy()

    # Merge into one list of places
    df = pd.concat([df_eateries, df_pois], ignore_index=True)

    # Fix coordinates: Replace commas with dots
    df['Lat'] = df['Lat'].astype(str).str.replace(',', '.').astype(float)
    df['Lon'] = df['Lon'].astype(str).str.replace(',', '.').astype(float)

    print(f"Loaded {len(df)} places.")
    print(f"Sample coordinate: {df.iloc[0]['Lat']}, {df.iloc[0]['Lon']}")
    return df

# ==========================================
# 2. ROUTE CALCULATION ENGINE
# ==========================================
OSRM_URL = "http://127.0.0.1:5000/route/v1/driving/"

def get_route(origin_coord, dest_coord):
    """
    Get route between two points from OSRM server.
    Returns encoded polyline string.
    """
    lon1, lat1 = origin_coord
    lon2, lat2 = dest_coord
    
    url = f"{OSRM_URL}{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
    
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data['code'] == 'Ok' and data['routes']:
                route = data['routes'][0]
                # Convert GeoJSON coordinates [lon, lat] to [lat, lon] for polyline encoding
                coords = [[lat, lon] for lon, lat in route['geometry']['coordinates']]
                encoded_polyline = polyline.encode(coords, 5)
                return encoded_polyline
        return None
    except Exception as e:
        print(f"Error getting route: {e}")
        return None

def calculate_all_routes(df_places):
    """
    Calculate routes from each place to all other places.
    Returns list of route records.
    """
    coords = df_places[['Lon', 'Lat']].values.tolist()
    ids = df_places['ID'].tolist()
    n = len(coords)
    
    routes_data = []
    total_routes = n * (n - 1)  # All pairs excluding self-routes
    processed = 0
    
    print(f"Starting route calculation for {n} locations ({total_routes} routes)...")
    start_time = time.time()
    
    for i in range(n):
        origin_id = ids[i]
        origin_coord = coords[i]
        
        for j in range(n):
            if i == j:
                # Skip self-routes
                continue
            
            dest_id = ids[j]
            dest_coord = coords[j]
            
            encoded_polyline = get_route(origin_coord, dest_coord)
            
            routes_data.append({
                'origin_id': origin_id,
                'dest_id': dest_id,
                'polyline': encoded_polyline
            })
            
            processed += 1
            if processed % 500 == 0:
                print(f"Progress: {processed}/{total_routes} ({100*processed/total_routes:.1f}%)", flush=True)
            
            # Small delay to avoid overwhelming the server
            time.sleep(0.01)
    
    return routes_data

# ==========================================
# 3. SAVE TO SQLITE
# ==========================================
def save_to_sqlite(routes_data, db_filename):
    """
    Save routes data to SQLite database with indexed queries.
    """
    print(f"\nSaving to SQLite database: {db_filename}")
    
    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()
    
    # Create table with minimal schema
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS routes (
            origin_id TEXT NOT NULL,
            dest_id TEXT NOT NULL,
            polyline TEXT,
            PRIMARY KEY (origin_id, dest_id)
        )
    ''')
    
    # Create index for fast lookups
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_origin ON routes(origin_id)')
    
    # Insert data
    cursor.executemany('''
        INSERT OR REPLACE INTO routes (origin_id, dest_id, polyline)
        VALUES (:origin_id, :dest_id, :polyline)
    ''', routes_data)
    
    conn.commit()
    
    # Get database statistics
    cursor.execute('SELECT COUNT(*) FROM routes')
    total_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM routes WHERE polyline IS NOT NULL')
    success_count = cursor.fetchone()[0]
    
    conn.close()
    
    return total_count, success_count

# ==========================================
# 4. EXECUTION
# ==========================================
if __name__ == "__main__":
    # A. Prepare Data
    df_places = load_and_clean_data()
    
    # B. Run Route Calculation
    print("\nStarting route calculation...")
    start_time = time.time()
    routes_data = calculate_all_routes(df_places)
    
    # C. Save to SQLite
    output_db = "dalat_routes.db"
    total_count, success_count = save_to_sqlite(routes_data, output_db)
    
    print(f"\n{'='*60}")
    print(f"Done! Saved to '{output_db}'")
    print(f"Total routes: {total_count}")
    print(f"Successful routes: {success_count}")
    print(f"Failed routes: {total_count - success_count}")
    print(f"Total time: {time.time() - start_time:.2f} seconds ({(time.time() - start_time)/60:.2f} minutes)")
    print(f"Average time per route: {(time.time() - start_time)/total_count:.3f} seconds")
    print(f"{'='*60}")
    
    # D. Query example
    print("\nExample queries:")
    conn = sqlite3.connect(output_db)
    cursor = conn.cursor()
    
    # Show first 5 routes
    print("\nFirst 5 routes:")
    cursor.execute('SELECT origin_id, dest_id, substr(polyline, 1, 50) as polyline_preview FROM routes LIMIT 5')
    for row in cursor.fetchall():
        print(f"  {row[0]} -> {row[1]}: {row[2]}...")
    
    # Show a specific route
    print("\nExample: Get route from E001 to P001:")
    cursor.execute('''
        SELECT origin_id, dest_id, polyline 
        FROM routes 
        WHERE origin_id = 'E001' AND dest_id = 'P001'
    ''')
    result = cursor.fetchone()
    if result:
        print(f"  {result[0]} -> {result[1]}")
        print(f"  Polyline: {result[2][:100]}...")
    
    conn.close()
