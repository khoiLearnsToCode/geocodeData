"""
Calculate routes from accommodations to POIs/Eateries using local OSRM server
and save encoded polylines to dalat_routes.db (preserving existing routes)
"""

import sqlite3
import pandas as pd
import requests
import time

# OSRM server URL
OSRM_URL = "http://127.0.0.1:5000/route/v1/driving/"

def load_data():
    """Load all location data"""
    print("=" * 60)
    print("LOADING DATA")
    print("=" * 60)
    
    # Load accommodations from database
    conn = sqlite3.connect('dalat_accommodations.db')
    df_acc = pd.read_sql_query("SELECT * FROM accommodations", conn)
    conn.close()
    print(f"✓ Loaded {len(df_acc)} accommodations")
    
    # Load eateries
    df_eat = pd.read_csv('dalat_eateries.csv')
    df_eat['Lat'] = df_eat['Lat'].astype(str).str.replace(',', '.').astype(float)
    df_eat['Lon'] = df_eat['Lon'].astype(str).str.replace(',', '.').astype(float)
    df_eat = df_eat[['ID', 'Lat', 'Lon']].rename(columns={'ID': 'id', 'Lat': 'lat', 'Lon': 'lon'})
    print(f"✓ Loaded {len(df_eat)} eateries")
    
    # Load POIs
    df_poi = pd.read_csv('dalat_pois.csv')
    df_poi['Lat'] = df_poi['Lat'].astype(str).str.replace(',', '.').astype(float)
    df_poi['Lon'] = df_poi['Lon'].astype(str).str.replace(',', '.').astype(float)
    df_poi = df_poi[['ID', 'Lat', 'Lon']].rename(columns={'ID': 'id', 'Lat': 'lat', 'Lon': 'lon'})
    print(f"✓ Loaded {len(df_poi)} POIs")
    
    # Combine eateries and POIs
    df_pois_eateries = pd.concat([df_eat, df_poi], ignore_index=True)
    print(f"✓ Total POIs/Eateries: {len(df_pois_eateries)}")
    
    return df_acc, df_pois_eateries

def get_route_osrm(lat1, lon1, lat2, lon2):
    """Get encoded polyline route from OSRM server"""
    url = f"{OSRM_URL}{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=polyline"
    
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('code') == 'Ok' and data.get('routes'):
                polyline = data['routes'][0]['geometry']
                return polyline
    except Exception as e:
        print(f"Error: {e}")
    
    return None

def calculate_accommodation_routes(df_acc, df_pois_eateries):
    """Calculate routes from accommodations to POIs/Eateries (both directions)"""
    print("\n" + "=" * 60)
    print("CALCULATING ACCOMMODATION <-> POI/EATERY ROUTES")
    print("=" * 60)
    
    # Calculate both directions: A->P and P->A
    total_calculations = len(df_acc) * len(df_pois_eateries) * 2
    print(f"Total calculations needed: {total_calculations} (both directions)")
    
    routes = []
    count = 0
    failed = 0
    
    # Direction 1: Accommodation -> POI/Eatery
    print("\nCalculating Accommodation -> POI/Eatery routes...")
    for _, acc in df_acc.iterrows():
        for _, poi in df_pois_eateries.iterrows():
            count += 1
            
            if count % 100 == 0:
                print(f"Progress: {count}/{total_calculations} ({count*100//total_calculations}%)")
            
            polyline = get_route_osrm(acc['lat'], acc['lon'], poi['lat'], poi['lon'])
            
            if polyline is not None:
                routes.append({
                    'origin_id': acc['id'],
                    'dest_id': poi['id'],
                    'polyline': polyline
                })
            else:
                failed += 1
            
            # Rate limiting
            time.sleep(0.01)
    
    # Direction 2: POI/Eatery -> Accommodation
    print("\nCalculating POI/Eatery -> Accommodation routes...")
    for _, poi in df_pois_eateries.iterrows():
        for _, acc in df_acc.iterrows():
            count += 1
            
            if count % 100 == 0:
                print(f"Progress: {count}/{total_calculations} ({count*100//total_calculations}%)")
            
            polyline = get_route_osrm(poi['lat'], poi['lon'], acc['lat'], acc['lon'])
            
            if polyline is not None:
                routes.append({
                    'origin_id': poi['id'],
                    'dest_id': acc['id'],
                    'polyline': polyline
                })
            else:
                failed += 1
            
            # Rate limiting
            time.sleep(0.01)
    
    print(f"✓ Completed: {len(routes)} routes calculated")
    if failed > 0:
        print(f"⚠ Failed: {failed} calculations")
    
    return routes

def update_routes_database(routes):
    """Update dalat_routes.db with new routes (preserving existing routes)"""
    print("\n" + "=" * 60)
    print("UPDATING DALAT_ROUTES.DB")
    print("=" * 60)
    
    conn = sqlite3.connect('dalat_routes.db')
    cursor = conn.cursor()
    
    # Create routes table if not exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS routes (
            origin_id TEXT,
            dest_id TEXT,
            polyline TEXT,
            PRIMARY KEY (origin_id, dest_id)
        )
    ''')
    
    # Create indexes if not exist
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_routes_origin ON routes(origin_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_routes_dest ON routes(dest_id)
    ''')
    
    # Get count of existing routes
    cursor.execute('SELECT COUNT(*) FROM routes')
    existing_count = cursor.fetchone()[0]
    print(f"Existing routes in database: {existing_count}")
    
    # Insert new routes (will replace if key exists)
    print("Inserting new accommodation routes...")
    inserted = 0
    for route in routes:
        cursor.execute('''
            INSERT OR REPLACE INTO routes (origin_id, dest_id, polyline)
            VALUES (?, ?, ?)
        ''', (route['origin_id'], route['dest_id'], route['polyline']))
        inserted += 1
        
        if inserted % 1000 == 0:
            conn.commit()
            print(f"  Inserted {inserted}/{len(routes)} routes...")
    
    conn.commit()
    
    # Get final statistics
    cursor.execute('SELECT COUNT(*) FROM routes')
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT origin_id) FROM routes')
    origins = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT dest_id) FROM routes')
    dests = cursor.fetchone()[0]
    
    # Check for accommodation routes
    cursor.execute("SELECT COUNT(*) FROM routes WHERE origin_id LIKE 'A%'")
    acc_as_origin = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM routes WHERE dest_id LIKE 'A%'")
    acc_as_dest = cursor.fetchone()[0]
    
    conn.close()
    
    print("=" * 60)
    print("SUCCESS!")
    print("=" * 60)
    print(f"✓ Previous routes: {existing_count}")
    print(f"✓ New routes added: {inserted}")
    print(f"✓ Total routes in database: {total:,}")
    print(f"✓ Unique origins: {origins}")
    print(f"✓ Unique destinations: {dests}")
    print(f"✓ Routes from accommodations: {acc_as_origin}")
    print(f"✓ Routes to accommodations: {acc_as_dest}")
    print(f"✓ Database: dalat_routes.db")
    
    return total

def main():
    # Load data
    df_acc, df_pois_eateries = load_data()
    
    # Calculate accommodation to POI/Eatery routes
    routes = calculate_accommodation_routes(df_acc, df_pois_eateries)
    
    # Update routes database
    total = update_routes_database(routes)
    
    print("\n" + "=" * 60)
    print("SAMPLE QUERIES")
    print("=" * 60)
    print("\nTo query routes, use:")
    print("  SELECT * FROM routes WHERE origin_id = 'A001' LIMIT 5;")
    print("  SELECT * FROM routes WHERE origin_id = 'A001' AND dest_id = 'E001';")
    print("  SELECT dest_id, LENGTH(polyline) as route_length FROM routes WHERE origin_id = 'A001' ORDER BY route_length LIMIT 5;")

if __name__ == "__main__":
    main()
