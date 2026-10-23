#!/usr/bin/env python3
"""
Convert nodes and edges from XML files (REA and REH) to CSV format.
Extracts geometry from polygons by creating a centerline from averaged polygon sides.
This is the preferred converter for the dashboard CSV format.

Usage: python tools/convert_xml_to_csv.py
Reads data/airspace/xml/ and writes data/airspace/nodes_edges_{reh,rea,combined}.csv.
"""

import xml.etree.ElementTree as ET
import csv
from pathlib import Path
from collections import defaultdict

FT_TO_M = 1 / 3.28084


def parse_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def feet_to_meters(value):
    return value * FT_TO_M


def clean_name(value, fallback):
    value = (value or "").strip()
    return value if value else fallback


def extract_vertical_profile(cv_element, ica_ns):
    """
    Extract altitude and corridor height in meters.
    Prefer fixed altitude, then generic bands, then A-to-B directional bands,
    then B-to-A bands as a final fallback.
    """
    altcomp = parse_float(cv_element.findtext(f'{ica_ns}altcomp', ''))
    altitude = feet_to_meters(altcomp) if altcomp is not None else None

    selected_band = None
    for max_field, min_field in [
        ('altmax', 'altmin'),
        ('altmaxa_to_b', 'altmina_to_b'),
        ('altmaxb_to_a', 'altminb_to_a')
    ]:
        altmax = parse_float(cv_element.findtext(f'{ica_ns}{max_field}', ''))
        altmin = parse_float(cv_element.findtext(f'{ica_ns}{min_field}', ''))
        if altmax is not None and altmin is not None:
            selected_band = (altmax, altmin)
            break

    height = None
    if selected_band:
        altmax, altmin = selected_band
        if altitude is None:
            altitude = feet_to_meters((altmax + altmin) / 2)
        height_ft = altmax - altmin
        if height_ft > 0:
            height = feet_to_meters(height_ft)

    return altitude, height


def extract_polygon_centerline(coord_string, fixo_a, fixo_b):
    """
    Extract centerline from polygon coordinates representing a corridor boundary:
    The polygon is a closed loop: fixo_a -> side1 -> fixo_b -> side2 -> fixo_a
    We extract both sides and average them to get the centerline.
    """
    if not coord_string or coord_string.strip() == "":
        return []
    
    # Parse coordinates: format is "lon,lat lon,lat ..." (space-separated)
    coords = []
    parts = coord_string.strip().split()
    
    for part in parts:
        if ',' in part:
            try:
                lon, lat = part.split(',')
                coords.append((float(lat), float(lon)))
            except ValueError:
                continue
    
    if len(coords) < 3:
        return coords
    
    # Remove the last point if it's the same as the first (closes the polygon)
    if coords[0] == coords[-1]:
        coords = coords[:-1]
    
    if len(coords) < 2:
        return coords
    
    # Find fixo_a and fixo_b in the polygon coordinates
    a_idx = -1
    b_idx = -1
    tolerance = 0.0001  # Account for 4-decimal-place rounding in polygon coords (~10 meters)
    
    for i, coord in enumerate(coords):
        dist_to_a = ((coord[0] - fixo_a[0])**2 + (coord[1] - fixo_a[1])**2)**0.5
        dist_to_b = ((coord[0] - fixo_b[0])**2 + (coord[1] - fixo_b[1])**2)**0.5
        
        if a_idx == -1 and dist_to_a < tolerance:
            a_idx = i
        if b_idx == -1 and dist_to_b < tolerance:
            b_idx = i
    
    # If we can't find fixo_a or fixo_b, fall back to the old algorithm
    if a_idx == -1 or b_idx == -1:
        n = len(coords)
        mid = n // 2
        side1 = coords[:mid]
        side2 = coords[mid:]
        side2_reversed = list(reversed(side2))
        centerline = []
        for i in range(min(len(side1), len(side2_reversed))):
            lat_avg = (side1[i][0] + side2_reversed[i][0]) / 2
            lon_avg = (side1[i][1] + side2_reversed[i][1]) / 2
            centerline.append((lat_avg, lon_avg))
        return centerline
    
    # Extract the two sides of the corridor
    # Side 1: from fixo_a to fixo_b (direct path)
    if a_idx < b_idx:
        side1 = coords[a_idx:b_idx+1]
    else:
        # fixo_b comes before fixo_a, so path goes: a->end, then wrap to b
        side1 = coords[a_idx:] + coords[:b_idx+1]
    
    # Side 2: from fixo_b back to fixo_a (going the other way around the polygon)
    if b_idx < a_idx:
        side2 = coords[b_idx:a_idx+1]
    else:
        # a comes before b, so reverse path goes: b->end, then wrap to a
        side2 = coords[b_idx:] + coords[:a_idx+1]
    
    # Reverse side2 so they're aligned in opposite directions
    side2_reversed = list(reversed(side2))
    
    # Average the sides to create the centerline
    centerline = []
    for i in range(min(len(side1), len(side2_reversed))):
        lat_avg = (side1[i][0] + side2_reversed[i][0]) / 2
        lon_avg = (side1[i][1] + side2_reversed[i][1]) / 2
        centerline.append((lat_avg, lon_avg))
    
    return centerline


def extract_routes_from_xml(xml_file, route_prefix):
    """
    Extract complete routes from XML file, one route per featureMember.
    Returns list of route dictionaries with altitude as None if missing (for later processing).
    """
    routes = []
    
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        ica_ns = '{https://geoaisweb.decea.mil.br/geoserver/ICA}'
        gml_ns = '{http://www.opengis.net/gml}'
        
        # Find all feature members
        feature_members = root.findall(f'.//{gml_ns}featureMember')
        
        print(f"Processing {xml_file}: Found {len(feature_members)} feature members")
        
        for feature_idx, feature in enumerate(feature_members):
            # Get the CV element
            cv_element = feature.find(f'.//{ica_ns}CV_REA_XP1_SAO_PAULO')
            if cv_element is None:
                cv_element = feature.find(f'.//{ica_ns}CV_REH_XP_SAO_PAULO')
            
            if cv_element is None:
                continue
            
            # Extract route metadata
            route_name = cv_element.findtext(f'{ica_ns}nome', '')
            
            # Extract start point (fixo_a)
            fixo_a_lat = cv_element.findtext(f'{ica_ns}fixo_a_lat', '')
            fixo_a_lon = cv_element.findtext(f'{ica_ns}fixo_a_lon', '')
            fixo_a_nome_raw = cv_element.findtext(f'{ica_ns}fixo_a_nome', '')
            
            # Extract end point (fixo_b)
            fixo_b_lat = cv_element.findtext(f'{ica_ns}fixo_b_lat', '')
            fixo_b_lon = cv_element.findtext(f'{ica_ns}fixo_b_lon', '')
            fixo_b_nome_raw = cv_element.findtext(f'{ica_ns}fixo_b_nome', '')
            fixo_a_nome = clean_name(fixo_a_nome_raw, f'{route_name} start')
            fixo_b_nome = clean_name(fixo_b_nome_raw, route_name or f'{fixo_a_nome} end')

            # Extract altitude and height (XML altitude values are in feet; CSV uses meters)
            altitude, height = extract_vertical_profile(cv_element, ica_ns)
            
            # Extract semi_largura (width = 2 × semi_largura)
            semi_largura = cv_element.findtext(f'{ica_ns}semi_largura', '0')
            try:
                width = float(semi_largura) * 2
            except ValueError:
                width = 0
            
            # Parse fixo_a and fixo_b coordinates first (needed for centerline extraction)
            try:
                lat_a = float(fixo_a_lat)
                lon_a = float(fixo_a_lon)
                lat_b = float(fixo_b_lat)
                lon_b = float(fixo_b_lon)
                fixo_a_tuple = (lat_a, lon_a)
                fixo_b_tuple = (lat_b, lon_b)
            except (ValueError, TypeError):
                continue
            
            # Extract geometry
            geom_elem = cv_element.find(f'{ica_ns}geom')
            if geom_elem is None:
                geom_elem = cv_element.find(f'{gml_ns}geom')
            
            polygon_coords = []
            if geom_elem is not None:
                # Try to find coordinates in the geometry
                coord_elem = geom_elem.find(f'.//{gml_ns}coordinates')
                if coord_elem is not None and coord_elem.text:
                    # Pass fixo_a and fixo_b to centerline extraction
                    polygon_coords = extract_polygon_centerline(coord_elem.text, fixo_a_tuple, fixo_b_tuple)
            
            # Create route record
            try:
                
                route = {
                    'name': route_name,
                    'fixo_a': fixo_a_tuple,
                    'fixo_a_nome': fixo_a_nome,
                    'fixo_b': fixo_b_tuple,
                    'fixo_b_nome': fixo_b_nome,
                    'polygon_coords': polygon_coords,
                    'altitude': altitude,  # Can be None for fallback processing
                    'width': width,
                    'height': height  # Can be None for fallback processing
                }
                routes.append(route)
            except (ValueError, TypeError) as e:
                print(f"  Error processing feature {feature_idx}: {e}")
                continue
        
        print(f"  Extracted {len(routes)} route segments")
        
    except Exception as e:
        print(f"Error processing {xml_file}: {e}")
    
    return routes


def route_to_records(route, route_full_name):
    """
    Convert a route (with polygon geometry) to CSV records (nodes only).
    Edges are implicit connections between consecutive nodes.
    Intelligently detects which endpoint (fixo_a or fixo_b) corresponds to start/end.
    """
    records = []
    coords = route['polygon_coords']
    
    if not coords:
        return records
    
    # Track which endpoint should be at which position
    start_endpoint = route['fixo_a']
    end_endpoint = route['fixo_b']
    start_name = route['fixo_a_nome']
    end_name = route['fixo_b_nome']
    
    # Intelligently determine which endpoint is which by calculating distances
    if len(coords) > 1:
        dist_a_to_first = ((route['fixo_a'][0] - coords[0][0])**2 + (route['fixo_a'][1] - coords[0][1])**2)**0.5
        dist_a_to_last = ((route['fixo_a'][0] - coords[-1][0])**2 + (route['fixo_a'][1] - coords[-1][1])**2)**0.5
        
        # If fixo_a is closer to the last point, swap them
        if dist_a_to_last < dist_a_to_first:
            start_endpoint = route['fixo_b']
            end_endpoint = route['fixo_a']
            start_name = route['fixo_b_nome']
            end_name = route['fixo_a_nome']
    
    seq_id = 1
    geometric_node_count = 0
    
    # Add first node (start endpoint - waypoint)
    records.append({
        'id': seq_id,
        'name': start_name,
        'lat': start_endpoint[0],
        'lon': start_endpoint[1],
        'type': 'Node',
        'altitude': route['altitude'],
        'height': route['height'],
        'width': route['width']
    })
    seq_id += 1
    
    # Add intermediate nodes from polygon centerline (geometric nodes)
    for lat, lon in coords:
        # Skip points that match the start endpoint
        if ((lat - start_endpoint[0])**2 + (lon - start_endpoint[1])**2)**0.5 < 0.0001:
            continue
        
        # Skip points that match the end endpoint
        if ((lat - end_endpoint[0])**2 + (lon - end_endpoint[1])**2)**0.5 < 0.0001:
            continue
        
        # Add intermediate node (geometric node) with generated name
        geometric_node_count += 1
        gn_name = f"{route_full_name}_GN_{geometric_node_count}"
        
        records.append({
            'id': seq_id,
            'name': gn_name,
            'lat': lat,
            'lon': lon,
            'type': 'Node',
            'altitude': route['altitude'],
            'height': route['height'],
            'width': route['width']
        })
        seq_id += 1
    
    # Add last node (end endpoint - waypoint)
    records.append({
        'id': seq_id,
        'name': end_name,
        'lat': end_endpoint[0],
        'lon': end_endpoint[1],
        'type': 'Node',
        'altitude': route['altitude'],
        'height': route['height'],
        'width': route['width']
    })
    
    return records


def apply_altitude_and_height_fallback(routes, waypoint_altitude_map, mean_altitude, mean_height):
    """
    Apply altitude and height fallback logic:
    
    Altitude:
    1. If altitude is available, keep it
    2. If not, search for fixo_a altitude in waypoint_altitude_map
    3. If not found, use mean_altitude
    
    Height:
    1. If height is available (calculated from altmax-altmin), keep it
    2. If not, use mean_height for the prefix
    """
    for route in routes:
        # Altitude fallback
        if route['altitude'] is None:
            # Try to find altitude from fixo_a waypoint name
            fixo_a_nome = route['fixo_a_nome']
            if fixo_a_nome in waypoint_altitude_map:
                route['altitude'] = waypoint_altitude_map[fixo_a_nome]
            else:
                # Use mean altitude as fallback
                route['altitude'] = mean_altitude
        
        # Height fallback
        if route['height'] is None or route['height'] <= 0:
            route['height'] = mean_height


def main():
    base_path = Path(__file__).resolve().parents[1]   # repository root
    xml_path = base_path / 'data' / 'airspace' / 'xml'
    output_path = base_path / 'data' / 'airspace'
    output_path.mkdir(parents=True, exist_ok=True)
    
    files_to_process = [
        ('CV_REA_XP1_SAO_PAULO.xml', 'REA'),
        ('CV_REH_XP_SAO_PAULO.xml', 'REH')
    ]
    
    route_data = {}
    
    # First pass: extract all routes from all files
    all_routes_by_prefix = {}
    for filename, route_prefix in files_to_process:
        input_file = xml_path / filename
        
        if not input_file.exists():
            print(f"Warning: {filename} not found")
            continue
        
        print(f"\nProcessing {filename}...")
        routes = extract_routes_from_xml(input_file, route_prefix)
        all_routes_by_prefix[route_prefix] = routes
    
    # Second pass: build waypoint altitude maps per prefix and calculate mean per prefix
    waypoint_altitude_maps = {}  # Map of prefix -> altitude_map
    mean_altitudes = {}  # Map of prefix -> mean_altitude
    mean_heights = {}  # Map of prefix -> mean_height
    
    for prefix, routes in all_routes_by_prefix.items():
        waypoint_altitude_maps[prefix] = {}
        prefix_altitudes = []
        prefix_heights = []
        
        for route in routes:
            # Map waypoint names to altitudes (if altitude is known)
            # Keep REA and REH separate!
            if route['altitude'] is not None:
                waypoint_altitude_maps[prefix][route['fixo_a_nome']] = route['altitude']
                waypoint_altitude_maps[prefix][route['fixo_b_nome']] = route['altitude']
                prefix_altitudes.append(route['altitude'])
            
            # Collect heights for mean calculation
            if route['height'] is not None:
                prefix_heights.append(route['height'])
        
        # Calculate mean altitude per prefix
        mean_altitudes[prefix] = sum(prefix_altitudes) / len(prefix_altitudes) if prefix_altitudes else 0
        
        # Calculate mean height per prefix, fallback to 1000 ft if no heights available
        mean_heights[prefix] = sum(prefix_heights) / len(prefix_heights) if prefix_heights else (1000 / 3.28084)
    
    print(f"\nWaypoint altitude map sizes, mean altitudes, and mean heights:")
    for prefix in waypoint_altitude_maps:
        print(f"  {prefix}: {len(waypoint_altitude_maps[prefix])} altitude entries, mean alt: {mean_altitudes[prefix]:.2f}m, mean height: {mean_heights[prefix]:.2f}m")
    
    # Third pass: apply altitude and height fallback and convert to records
    for prefix, routes in all_routes_by_prefix.items():
        print(f"\nApplying altitude and height fallback for {prefix}...")
        apply_altitude_and_height_fallback(routes, waypoint_altitude_maps[prefix], mean_altitudes[prefix], mean_heights[prefix])
        
        # Convert routes to records
        all_records = []
        route_names = defaultdict(int)  # Track count of each route name
        
        for route_idx, route in enumerate(routes, 1):
            # Use route name from XML, with index to differentiate segments with same name
            route_name = route['name']
            route_names[route_name] += 1
            route_full_name = f"{route_name}_{route_names[route_name]}" if route_names[route_name] > 1 else route_name
            
            records = route_to_records(route, route_full_name)
            
            for record in records:
                all_records.append({
                    'route': route_full_name,
                    'id': record['id'],
                    'name': record['name'],
                    'lat': record['lat'],
                    'lon': record['lon'],
                    'type': record['type'],
                    'altitude': record['altitude'],
                    'height': record['height'],
                    'width': record['width']
                })
        
        route_data[prefix] = all_records
    
    # Write separate CSV files
    fieldnames = ['route', 'id', 'name', 'lat', 'lon', 'type', 'altitude', 'height', 'width']
    
    for route_prefix, records in route_data.items():
        if records:
            output_file = output_path / f'nodes_edges_{route_prefix.lower()}.csv'
            
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, lineterminator='\n')
                writer.writeheader()
                writer.writerows(records)
            
            print(f"Successfully wrote {len(records)} records to {output_file}")
    
    # Write combined file
    all_data = []
    for records in route_data.values():
        all_data.extend(records)
    
    if all_data:
        combined_file = output_path / 'nodes_edges_combined.csv'
        with open(combined_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, lineterminator='\n')
            writer.writeheader()
            writer.writerows(all_data)
        
        print(f"\nSuccessfully wrote {len(all_data)} records to combined file")


if __name__ == '__main__':
    main()
