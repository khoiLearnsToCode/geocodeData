from flask import Flask, render_template, request, jsonify
import sqlite3
import pandas as pd
import polyline

app = Flask(__name__)

# Load places data (including accommodations)
def get_places():
    # Load accommodations from database
    conn = sqlite3.connect('dalat_accommodations.db')
    df_accommodations = pd.read_sql_query("SELECT id, name_en as name, lat, lon FROM accommodations", conn)
    conn.close()
    
    # Load eateries
    df_eateries = pd.read_csv('dalat_eateries.csv')
    eateries = df_eateries[['ID', 'Tên quán', 'Lat', 'Lon']].copy()
    eateries.columns = ['id', 'name', 'lat', 'lon']
    
    # Load POIs
    df_pois = pd.read_csv('dalat_pois.csv')
    pois = df_pois[['ID', 'Tên địa điểm', 'Lat', 'Lon']].copy()
    pois.columns = ['id', 'name', 'lat', 'lon']
    
    # Combine all
    places = pd.concat([df_accommodations, eateries, pois], ignore_index=True)
    
    # Fix coordinates for eateries and POIs
    places['lat'] = places['lat'].astype(str).str.replace(',', '.').astype(float)
    places['lon'] = places['lon'].astype(str).str.replace(',', '.').astype(float)
    
    return places.to_dict('records')

def get_route(origin_id, dest_id):
    conn = sqlite3.connect('dalat_routes.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT polyline FROM routes 
        WHERE origin_id = ? AND dest_id = ?
    ''', (origin_id, dest_id))
    
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        # Decode polyline to coordinates
        coords = polyline.decode(result[0], 5)
        return coords
    return None

@app.route('/')
def index():
    places = get_places()
    return render_template('index.html', places=places)

@app.route('/get_route', methods=['POST'])
def route():
    data = request.get_json()
    origin_id = data.get('origin')
    dest_id = data.get('dest')
    
    if not origin_id or not dest_id:
        return jsonify({'error': 'Missing origin or destination'}), 400
    
    if origin_id == dest_id:
        return jsonify({'error': 'Origin and destination cannot be the same'}), 400
    
    # Get route coordinates
    route_coords = get_route(origin_id, dest_id)
    
    if route_coords:
        return jsonify({
            'success': True,
            'route': route_coords
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Route not found'
        }), 404

@app.route('/get_place_info', methods=['POST'])
def place_info():
    data = request.get_json()
    place_id = data.get('id')
    
    places = get_places()
    place = next((p for p in places if p['id'] == place_id), None)
    
    if place:
        return jsonify(place)
    else:
        return jsonify({'error': 'Place not found'}), 404

if __name__ == '__main__':
    app.run(debug=True, port=8080)
