"""
Calculate distances from accommodations to POIs/Eateries using local OSRM server
and create a unified distance database
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

def get_distance_osrm(lat1, lon1, lat2, lon2):
    """Get distance between two points from OSRM server (returns km)"""
    url = f"{OSRM_URL}{lon1},{lat1};{lon2},{lat2}?overview=false"
    
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('code') == 'Ok' and data.get('routes'):
                distance_m = data['routes'][0]['distance']
                return round(distance_m / 1000, 3)  # Convert to km
    except Exception as e:
        print(f"Error: {e}")
    
    return None

def calculate_accommodation_distances(df_acc, df_pois_eateries):
    """Calculate distances from accommodations to all POIs/Eateries (both directions)"""
    print("\n" + "=" * 60)
    print("CALCULATING ACCOMMODATION TO POI/EATERY DISTANCES")
    print("=" * 60)
    
    # Calculate both directions: A->P and P->A
    total_calculations = len(df_acc) * len(df_pois_eateries) * 2
    print(f"Total calculations needed: {total_calculations} (both directions)")
    
    distances = []
    count = 0
    failed = 0
    
    # Direction 1: Accommodation -> POI/Eatery
    print("\nCalculating Accommodation -> POI/Eatery...")
    for _, acc in df_acc.iterrows():
        for _, poi in df_pois_eateries.iterrows():
            count += 1
            
            if count % 100 == 0:
                print(f"Progress: {count}/{total_calculations} ({count*100//total_calculations}%)")
            
            dist = get_distance_osrm(acc['lat'], acc['lon'], poi['lat'], poi['lon'])
            
            if dist is not None:
                distances.append({
                    'origin_id': acc['id'],
                    'dest_id': poi['id'],
                    'distance_km': dist
                })
            else:
                failed += 1
            
            # Rate limiting
            time.sleep(0.01)
    
    # Direction 2: POI/Eatery -> Accommodation
    print("\nCalculating POI/Eatery -> Accommodation...")
    for _, poi in df_pois_eateries.iterrows():
        for _, acc in df_acc.iterrows():
            count += 1
            
            if count % 100 == 0:
                print(f"Progress: {count}/{total_calculations} ({count*100//total_calculations}%)")
            
            dist = get_distance_osrm(poi['lat'], poi['lon'], acc['lat'], acc['lon'])
            
            if dist is not None:
                distances.append({
                    'origin_id': poi['id'],
                    'dest_id': acc['id'],
                    'distance_km': dist
                })
            else:
                failed += 1
            
            # Rate limiting
            time.sleep(0.01)
    
    print(f"✓ Completed: {len(distances)} distances calculated")
    if failed > 0:
        print(f"⚠ Failed: {failed} calculations")
    
    return distances

def load_poi_eatery_distances():
    """Load existing POI/Eatery distance matrix from CSV"""
    print("\n" + "=" * 60)
    print("LOADING EXISTING POI/EATERY DISTANCES")
    print("=" * 60)
    
    df_matrix = pd.read_csv('dalat_distance_matrix_named.csv', index_col=0)
    print(f"✓ Loaded distance matrix: {df_matrix.shape[0]} x {df_matrix.shape[1]}")
    
    distances = []
    
    for origin_id in df_matrix.index:
        for dest_id in df_matrix.columns:
            dist = df_matrix.loc[origin_id, dest_id]
            if pd.notna(dist) and dist > 0:
                distances.append({
                    'origin_id': origin_id,
                    'dest_id': dest_id,
                    'distance_km': float(dist)
                })
    
    print(f"✓ Extracted {len(distances)} distances from matrix")
    return distances

def create_unified_database(acc_distances, poi_distances):
    """Create unified SQLite database with all distances"""
    print("\n" + "=" * 60)
    print("CREATING UNIFIED DISTANCE DATABASE")
    print("=" * 60)
    
    conn = sqlite3.connect('dalat_distances.db')
    cursor = conn.cursor()
    
    # Create distances table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS distances (
            origin_id TEXT,
            dest_id TEXT,
            distance_km REAL,
            PRIMARY KEY (origin_id, dest_id)
        )
    ''')
    
    # Create index for faster queries
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_origin ON distances(origin_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_dest ON distances(dest_id)
    ''')
    
    # Clear existing data
    cursor.execute('DELETE FROM distances')
    
    print("Inserting accommodation distances...")
    for dist in acc_distances:
        cursor.execute('''
            INSERT OR REPLACE INTO distances (origin_id, dest_id, distance_km)
            VALUES (?, ?, ?)
        ''', (dist['origin_id'], dist['dest_id'], dist['distance_km']))
    
    print("Inserting POI/Eatery distances...")
    for dist in poi_distances:
        cursor.execute('''
            INSERT OR REPLACE INTO distances (origin_id, dest_id, distance_km)
            VALUES (?, ?, ?)
        ''', (dist['origin_id'], dist['dest_id'], dist['distance_km']))
    
    conn.commit()
    
    # Get statistics
    cursor.execute('SELECT COUNT(*) FROM distances')
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT origin_id) FROM distances')
    origins = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT dest_id) FROM distances')
    dests = cursor.fetchone()[0]
    
    conn.close()
    
    print("=" * 60)
    print("SUCCESS!")
    print("=" * 60)
    print(f"✓ Total distances stored: {total:,}")
    print(f"✓ Unique origins: {origins}")
    print(f"✓ Unique destinations: {dests}")
    print(f"✓ Database: dalat_distances.db")
    
    return total

def main():
    # Load data
    df_acc, df_pois_eateries = load_data()
    
    # Calculate accommodation to POI/Eatery distances
    acc_distances = calculate_accommodation_distances(df_acc, df_pois_eateries)
    
    # Load existing POI/Eatery distances
    poi_distances = load_poi_eatery_distances()
    
    # Create unified database
    total = create_unified_database(acc_distances, poi_distances)
    
    print("\n" + "=" * 60)
    print("SAMPLE QUERIES")
    print("=" * 60)
    print("\nTo query distances, use:")
    print("  SELECT * FROM distances WHERE origin_id = 'A001' LIMIT 10;")
    print("  SELECT * FROM distances WHERE origin_id = 'A001' AND dest_id = 'E001';")
    print("  SELECT dest_id, distance_km FROM distances WHERE origin_id = 'A001' ORDER BY distance_km LIMIT 5;")

if __name__ == "__main__":
    main()
