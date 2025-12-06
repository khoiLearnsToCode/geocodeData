"""
Extract accommodations in Dalat from LOCAL OSM PBF file and save to SQLite
Usage: python extract_accommodations.py
"""

import sqlite3
import osmium

# Dalat bounding box
DALAT_BBOX = {
    'min_lat': 11.88,
    'max_lat': 12.00,
    'min_lon': 108.40,
    'max_lon': 108.48
}

class AccommodationHandler(osmium.SimpleHandler):
    def __init__(self):
        osmium.SimpleHandler.__init__(self)
        self.accommodations = []
        self.counter = 0
    
    def is_in_dalat(self, lat, lon):
        """Check if coordinates are within Dalat bounds"""
        return (DALAT_BBOX['min_lat'] <= lat <= DALAT_BBOX['max_lat'] and
                DALAT_BBOX['min_lon'] <= lon <= DALAT_BBOX['max_lon'])
    
    def is_accommodation(self, tags):
        """Check if tags indicate accommodation"""
        if tags.get('tourism') in ['hotel', 'motel', 'hostel', 'guest_house', 
                                     'apartment', 'resort', 'chalet']:
            return True
        if tags.get('building') == 'hotel':
            return True
        return False
    
    def add_accommodation(self, tags, lat, lon):
        """Add accommodation to list"""
        # Skip if no name available
        name = tags.get('name:en', tags.get('name', ''))
        if not name or name.lower() == 'unknown':
            return
        
        self.counter += 1
        
        self.accommodations.append({
            'id': f'A{self.counter:03d}',
            'name_en': name,
            'name_vn': tags.get('name:vi', tags.get('name', '')),
            'lat': lat,
            'lon': lon
        })
    
    def node(self, n):
        """Process OSM nodes"""
        if not n.location.valid():
            return
            
        lat = n.location.lat
        lon = n.location.lon
        
        if not self.is_in_dalat(lat, lon):
            return
        
        tags = {tag.k: tag.v for tag in n.tags}
        
        if self.is_accommodation(tags):
            self.add_accommodation(tags, lat, lon)
    
    def way(self, w):
        """Process OSM ways"""
        if not w.nodes:
            return
            
        try:
            center = w.nodes[len(w.nodes)//2]
            if not center.location.valid():
                return
                
            lat = center.location.lat
            lon = center.location.lon
            
            if not self.is_in_dalat(lat, lon):
                return
            
            tags = {tag.k: tag.v for tag in w.tags}
            
            if self.is_accommodation(tags):
                self.add_accommodation(tags, lat, lon)
        except:
            pass

def extract_accommodations():
    """Extract accommodations from LOCAL OSM file"""
    
    print("=" * 60)
    print("EXTRACTING DALAT ACCOMMODATIONS FROM LOCAL OSM FILE")
    print("=" * 60)
    print(f"Bounding box: Lat {DALAT_BBOX['min_lat']}-{DALAT_BBOX['max_lat']}, "
          f"Lon {DALAT_BBOX['min_lon']}-{DALAT_BBOX['max_lon']}")
    
    handler = AccommodationHandler()
    
    print("\nProcessing vietnam-251124.osm.pbf...")
    print("This may take 1-2 minutes...")
    
    try:
        handler.apply_file("vietnam-251124.osm.pbf", locations=True)
        print(f"✓ Found {len(handler.accommodations)} accommodations!")
        
        save_to_database(handler.accommodations)
        
    except Exception as e:
        print(f"Error processing OSM file: {e}")

def save_to_database(accommodations):
    """Save accommodations to SQLite database"""
    
    if not accommodations:
        print("No accommodations found!")
        return
    
    print(f"Saving {len(accommodations)} accommodations to database...")
    
    # Create/connect to database
    conn = sqlite3.connect('dalat_accommodations.db')
    cursor = conn.cursor()
    
    # Create table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accommodations (
            id TEXT PRIMARY KEY,
            name_en TEXT,
            name_vn TEXT,
            lat REAL,
            lon REAL
        )
    ''')
    
    # Clear existing data
    cursor.execute('DELETE FROM accommodations')
    
    # Insert accommodations
    for acc in accommodations:
        cursor.execute('''
            INSERT INTO accommodations (id, name_en, name_vn, lat, lon)
            VALUES (?, ?, ?, ?, ?)
        ''', (acc['id'], acc['name_en'], acc['name_vn'], acc['lat'], acc['lon']))
    
    conn.commit()
    conn.close()
    
    print("=" * 60)
    print("SUCCESS!")
    print("=" * 60)
    print(f"✓ Saved {len(accommodations)} accommodations")
    print("✓ Database: dalat_accommodations.db")
    print("\nSample entries:")
    for acc in accommodations[:5]:
        print(f"  {acc['id']}: {acc['name_en']} ({acc['lat']:.4f}, {acc['lon']:.4f})")

if __name__ == "__main__":
    extract_accommodations()
