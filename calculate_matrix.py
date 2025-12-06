import requests
import pandas as pd
import numpy as np
import time

# ==========================================
# 1. LOAD & CLEAN DATA
# ==========================================
def load_and_clean_data():
    print("Loading data...")
    # Load files
    df_eateries = pd.read_csv('dalat_eateries.csv')
    df_pois = pd.read_csv('dalat_pois.csv')

    # Standardize columns to merge them easily
    # We keep 'ID' and the coordinates. We'll use 'ID' as the label.
    df_eateries = df_eateries[['ID', 'Lat', 'Lon']].copy()
    df_pois = df_pois[['ID', 'Lat', 'Lon']].copy()

    # Merge into one list of places
    df = pd.concat([df_eateries, df_pois], ignore_index=True)

    # !!! CRITICAL FIX: Replace commas with dots for coordinates !!!
    # Example: '11,9464' -> '11.9464'
    df['Lat'] = df['Lat'].astype(str).str.replace(',', '.').astype(float)
    df['Lon'] = df['Lon'].astype(str).str.replace(',', '.').astype(float)

    print(f"Loaded {len(df)} places.")
    print(f"Sample coordinate: {df.iloc[0]['Lat']}, {df.iloc[0]['Lon']}")
    return df

# ==========================================
# 2. CALCULATION ENGINE
# ==========================================
OSRM_URL = "http://127.0.0.1:5000/table/v1/driving/"
CHUNK_SIZE = 50 # Keep at 50 to respect URL length limits

def get_matrix(df_places):
    coords = df_places[['Lon', 'Lat']].values.tolist() # OSRM expects [Lon, Lat]
    ids = df_places['ID'].tolist()
    n = len(coords)
    
    # Initialize matrix with infinity
    full_matrix = np.full((n, n), -1.0)
    
    print(f"Starting batch calculation for {n} locations...")
    
    for i in range(0, n, CHUNK_SIZE):
        for j in range(0, n, CHUNK_SIZE):
            # Create batches
            src_batch = coords[i : i + CHUNK_SIZE]
            dst_batch = coords[j : j + CHUNK_SIZE]
            
            # Prepare URL
            # 1. Combine all unique coords in this batch to minimize string length
            batch_coords = src_batch + dst_batch
            coord_str = ";".join([f"{lon},{lat}" for lon, lat in batch_coords])
            
            # 2. Map indices
            # Sources are the first part of the list, Destinations are the second part
            src_indices = ";".join(map(str, range(len(src_batch))))
            dst_indices = ";".join(map(str, range(len(src_batch), len(batch_coords))))
            
            url = f"{OSRM_URL}{coord_str}?sources={src_indices}&destinations={dst_indices}&annotations=distance"
            
            try:
                resp = requests.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if data['code'] == 'Ok':
                        distances = data['distances']
                        
                        # Fill main matrix
                        for r in range(len(src_batch)):
                            for c in range(len(dst_batch)):
                                dist_m = distances[r][c]
                                # Convert meters to KM
                                if dist_m is not None:
                                    full_matrix[i+r, j+c] = round(dist_m / 1000, 3)
                else:
                    print(f"Batch {i}-{j} failed: HTTP {resp.status_code}")
            except Exception as e:
                print(f"Connection Error: {e}")
                
            # Optional: nice progress bar
            print(f"Processed batch {i//CHUNK_SIZE}-{j//CHUNK_SIZE}", end='\r')

    return full_matrix, ids

# ==========================================
# 3. EXECUTION
# ==========================================
if __name__ == "__main__":
    # A. Prepare Data
    df_places = load_and_clean_data()
    
    # B. Run Calculation
    start_time = time.time()
    matrix_values, place_ids = get_matrix(df_places)
    
    # C. Save Output with Headers
    # This creates a table where Row Headers and Col Headers are the Place IDs
    df_output = pd.DataFrame(matrix_values, index=place_ids, columns=place_ids)
    
    output_filename = "dalat_distance_matrix_named.csv"
    df_output.to_csv(output_filename)
    
    print(f"\n\nDone! Saved to '{output_filename}'")
    print(f"Total time: {time.time() - start_time:.2f} seconds")