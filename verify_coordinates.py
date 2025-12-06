import pandas as pd
import requests
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from geopy.distance import geodesic
import time

# Initialize geolocator once globally
geolocator = Nominatim(user_agent="coordinate_verification_dalat", timeout=15)
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.5)
def geocode_place(name, address):
    """Geocode a place using geopy with Nominatim - using address only"""
    try:
        # Use address only for geocoding
        if address and isinstance(address, str) and address.strip() and address.lower() != 'n/a':
            search_query = address
        else:
            return None
        
        # Geocode the location
        location = geolocator.geocode(search_query)
        
        if location:
            # Check if it's reasonably close to Da Lat (lat ~12, lon ~108)
            if 11.5 < location.latitude < 12.5 and 107.5 < location.longitude < 109:
                return location.latitude, location.longitude
        
        return None
    except Exception as e:
        return None

def parse_coordinate(coord_str):
    """Parse coordinate string with commas to float"""
    try:
        # Handle coordinates with commas as decimal separators
        if isinstance(coord_str, str):
            # Remove quotes and convert comma to dot
            coord_str = coord_str.replace('"', '').replace(',', '.')
        return float(coord_str)
    except (ValueError, TypeError):
        return None

def verify_osrm_location(lat, lon):
    """Verify if coordinates are accessible via OSRM"""
    try:
        # Use OSRM nearest service to check if location is in the map
        url = f"http://localhost:5000/nearest/v1/driving/{lon},{lat}"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == 'Ok':
                return True
        return False
    except Exception as e:
        return False

def check_coordinates(csv_file, id_col, name_col, lat_col, lon_col, address_col):
    """Check all coordinates in a CSV file by geocoding place names"""
    print(f"\nProcessing {csv_file}...")
    
    # Read CSV
    df = pd.read_csv(csv_file)
    
    mismatches = []
    total = len(df)
    skipped = 0
    checked = 0
    
    for idx, row in df.iterrows():
        try:
            # Get ID, name, and address
            location_id = row[id_col]
            location_name = row[name_col]
            address = row.get(address_col, '') if address_col else ''
            
            # Parse database coordinates
            db_lat = parse_coordinate(row[lat_col])
            db_lon = parse_coordinate(row[lon_col])
            
            if db_lat is None or db_lon is None:
                print(f"Skipping {location_id} - {location_name}: Invalid coordinates in database")
                skipped += 1
                continue
            
            print(f"Checking [{idx+1}/{total}] {location_id} - {location_name}...", end=" ")
            
            # Geocode the place to get real coordinates
            geocoded = geocode_place(location_name, address)
            
            if geocoded is None:
                print("SKIP (Geocoding failed)")
                skipped += 1
                time.sleep(1.5)  # Respect Nominatim rate limit
                continue
            
            real_lat, real_lon = geocoded
            
            # Verify that the geocoded location is in OSRM map
            if not verify_osrm_location(real_lat, real_lon):
                print("SKIP (Not in OSRM map)")
                skipped += 1
                time.sleep(1.5)  # Respect Nominatim rate limit
                continue
            
            # Calculate distance using geopy's geodesic (more accurate than haversine)
            db_point = (db_lat, db_lon)
            real_point = (real_lat, real_lon)
            distance = geodesic(db_point, real_point).meters
            
            print(f"{distance:.1f}m", end="")
            
            if distance > 750:
                print(" ❌ MISMATCH")
                mismatches.append({
                    'ID': location_id,
                    'Name': location_name,
                    'Database_Lat': db_lat,
                    'Database_Lon': db_lon,
                    'Real_Lat': real_lat,
                    'Real_Lon': real_lon,
                    'Distance_m': round(distance, 2)
                })
            else:
                print(" ✓")
            
            checked += 1
            
            # Respect Nominatim usage policy (max 1 request per second)
            time.sleep(1.5)
            
        except Exception as e:
            print(f"Error processing {location_id}: {e}")
            skipped += 1
            continue
    
    print(f"\nSummary for {csv_file}:")
    print(f"  Total: {total}")
    print(f"  Checked: {checked}")
    print(f"  Skipped: {skipped}")
    print(f"  Mismatches: {len(mismatches)}")
    
    return mismatches

def main():
    print("=" * 80)
    print("COORDINATE VERIFICATION TOOL")
    print("Geocoding place names and comparing with database coordinates")
    print("Using geopy with Nominatim and geodesic distance")
    print("Threshold: 750 meters")
    print("=" * 80)
    
    all_mismatches = []
    
    # Check POIs
    try:
        print("\n" + "=" * 80)
        print("CHECKING POIS")
        print("=" * 80)
        pois_mismatches = check_coordinates(
            csv_file='dalat_pois.csv',
            id_col='ID',
            name_col='Tên địa điểm',
            lat_col='Lat',
            lon_col='Lon',
            address_col='Địa chỉ'
        )
        all_mismatches.extend(pois_mismatches)
    except Exception as e:
        print(f"Error processing POIs: {e}")
    
    # Check Eateries
    try:
        print("\n" + "=" * 80)
        print("CHECKING EATERIES")
        print("=" * 80)
        eateries_mismatches = check_coordinates(
            csv_file='dalat_eateries.csv',
            id_col='ID',
            name_col='Tên quán',
            lat_col='Lat',
            lon_col='Lon',
            address_col='Địa chỉ'
        )
        all_mismatches.extend(eateries_mismatches)
    except Exception as e:
        print(f"Error processing Eateries: {e}")
    
    # Write results to file
    if all_mismatches:
        print(f"\n{'=' * 80}")
        print(f"WRITING RESULTS TO mismatch.txt")
        print(f"{'=' * 80}\n")
        
        with open('mismatch.txt', 'w', encoding='utf-8') as f:
            f.write("COORDINATE MISMATCHES (>750m from geocoded real location)\n")
            f.write("=" * 80 + "\n\n")
            
            for m in all_mismatches:
                f.write(f"ID: {m['ID']}\n")
                f.write(f"Name: {m['Name']}\n")
                f.write(f"Database Coordinates: {m['Database_Lat']}, {m['Database_Lon']}\n")
                f.write(f"Real Coordinates (geocoded): {m['Real_Lat']}, {m['Real_Lon']}\n")
                f.write(f"Distance: {m['Distance_m']} meters\n")
                f.write("-" * 80 + "\n\n")
        
        print(f"Found {len(all_mismatches)} total mismatches!")
        print("Results written to mismatch.txt")
    else:
        print("\n✓ No mismatches found! All coordinates are within 750m threshold.")

if __name__ == "__main__":
    main()
