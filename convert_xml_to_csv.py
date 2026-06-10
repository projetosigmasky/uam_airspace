#!/usr/bin/env python3
"""
Convert nodes and edges from XML files (REA and REH) to CSV format.
Nodes are ordered by edge connectivity to form routes.
When connectivity is broken, a new route segment is created (e.g., REA_1, REA_2).
"""

import xml.etree.ElementTree as ET
import csv
import os
from pathlib import Path
from collections import defaultdict

def extract_nodes_and_edges(xml_file, route_name):
    """
    Extract nodes and edges from XML file, building connected routes.
    Returns a list of records organized by connected paths.
    """
    all_records = []
    
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        # Define namespaces
        namespaces = {
            'gml': 'http://www.opengis.net/gml',
            'ICA': 'https://geoaisweb.decea.mil.br/geoserver/ICA'
        }
        
        # Find all feature members
        feature_members = root.findall('.//gml:featureMember', namespaces)
        
        print(f"Processing {xml_file}: Found {len(feature_members)} feature members")
        
        # Extract all edges first
        edges = []
        node_dict = {}  # key: (lat, lon), value: node_name
        
        for feature in feature_members:
            # Get the CV element (contains the edge/corridor definition)
            cv_element = feature.find('.//{https://geoaisweb.decea.mil.br/geoserver/ICA}CV_REA_XP1_SAO_PAULO')
            if cv_element is None:
                cv_element = feature.find('.//{https://geoaisweb.decea.mil.br/geoserver/ICA}CV_REH_XP_SAO_PAULO')
            
            if cv_element is None:
                continue
            
            # Extract edge information
            ica_ns = '{https://geoaisweb.decea.mil.br/geoserver/ICA}'
            nome = cv_element.findtext(f'{ica_ns}nome', '')
            fixo_a_lat_str = cv_element.findtext(f'{ica_ns}fixo_a_lat', '')
            fixo_a_lon_str = cv_element.findtext(f'{ica_ns}fixo_a_lon', '')
            fixo_b_lat_str = cv_element.findtext(f'{ica_ns}fixo_b_lat', '')
            fixo_b_lon_str = cv_element.findtext(f'{ica_ns}fixo_b_lon', '')
            fixo_a_nome = cv_element.findtext(f'{ica_ns}fixo_a_nome', '')
            fixo_b_nome = cv_element.findtext(f'{ica_ns}fixo_b_nome', '')
            
            # Try to get altitude
            altcomp_str = cv_element.findtext(f'{ica_ns}altcomp', '')
            altmax_str = cv_element.findtext(f'{ica_ns}altmax', '')
            altmaxa_to_b_str = cv_element.findtext(f'{ica_ns}altmaxa_to_b', '')
            altmin_str = cv_element.findtext(f'{ica_ns}altmin', '')
            altmina_to_b_str = cv_element.findtext(f'{ica_ns}altmina_to_b', '')
            
            altitude = None
            if altcomp_str:
                try:
                    altitude = float(altcomp_str)
                except ValueError:
                    pass
            if altitude is None and altmaxa_to_b_str:
                try:
                    altitude = float(altmaxa_to_b_str)
                except ValueError:
                    pass
            if altitude is None and altmax_str:
                try:
                    altitude = float(altmax_str)
                except ValueError:
                    pass
            if altitude is None and altmina_to_b_str:
                try:
                    altitude = float(altmina_to_b_str)
                except ValueError:
                    pass
            if altitude is None and altmin_str:
                try:
                    altitude = float(altmin_str)
                except ValueError:
                    pass
            
            altitude = altitude if altitude is not None else 0
            
            # Process nodes and edges
            try:
                lat_a = float(fixo_a_lat_str)
                lon_a = float(fixo_a_lon_str)
                lat_b = float(fixo_b_lat_str)
                lon_b = float(fixo_b_lon_str)
                
                # Store node names
                key_a = (lat_a, lon_a)
                key_b = (lat_b, lon_b)
                
                if key_a not in node_dict:
                    node_dict[key_a] = fixo_a_nome
                if key_b not in node_dict:
                    node_dict[key_b] = fixo_b_nome
                
                # Create edge record
                edges.append({
                    'node_a': key_a,
                    'node_b': key_b,
                    'name_a': fixo_a_nome,
                    'name_b': fixo_b_nome,
                    'edge_name': nome,
                    'altitude': altitude
                })
            except (ValueError, TypeError):
                pass
        
        print(f"  Found {len(edges)} edges and {len(node_dict)} unique nodes")
        
        # Build connected routes by tracing edges
        routes = build_connected_routes(edges, node_dict, route_name)
        
        # Convert routes to records
        for route_idx, route_path in enumerate(routes, 1):
            current_route_name = f"{route_name}_{route_idx}" if len(routes) > 1 else route_name
            
            for record in route_path:
                all_records.append({
                    'route': current_route_name,
                    'id': record['seq_id'],
                    'name': record['name'],
                    'lat': record['lat'],
                    'lon': record['lon'],
                    'type': record['type'],
                    'altitude': record['altitude'],
                    'height': 30.48,
                    'width': 30.48
                })
        
    except Exception as e:
        print(f"Error processing {xml_file}: {e}")
    
    return all_records


def build_connected_routes(edges, node_dict, route_name):
    """
    Build connected routes by tracing edge connectivity.
    Returns a list of routes, where each route is a list of node and edge records.
    """
    routes = []
    used_edges = set()
    
    # Create adjacency list for edges
    node_edges = defaultdict(list)  # node -> list of (edge_idx, direction)
    
    for idx, edge in enumerate(edges):
        node_edges[edge['node_a']].append((idx, 'a'))
        node_edges[edge['node_b']].append((idx, 'b'))
    
    # Process each unused edge to start a new route
    for start_edge_idx in range(len(edges)):
        if start_edge_idx in used_edges:
            continue
        
        route_records = []
        current_node = None
        current_edge_idx = start_edge_idx
        seq_id = 1
        
        # Initialize with first edge
        edge = edges[start_edge_idx]
        used_edges.add(start_edge_idx)
        
        # Add first node
        route_records.append({
            'name': edge['name_a'],
            'lat': edge['node_a'][0],
            'lon': edge['node_a'][1],
            'type': 'Node',
            'altitude': edge['altitude'],
            'edge_name': edge['edge_name'],
            'seq_id': seq_id
        })
        seq_id += 1
        
        # Add first edge
        route_records.append({
            'name': edge['edge_name'],
            'lat': (edge['node_a'][0] + edge['node_b'][0]) / 2,
            'lon': (edge['node_a'][1] + edge['node_b'][1]) / 2,
            'type': 'Edge',
            'altitude': edge['altitude'],
            'edge_name': edge['edge_name'],
            'seq_id': seq_id
        })
        seq_id += 1
        
        # Add second node
        route_records.append({
            'name': edge['name_b'],
            'lat': edge['node_b'][0],
            'lon': edge['node_b'][1],
            'type': 'Node',
            'altitude': edge['altitude'],
            'edge_name': edge['edge_name'],
            'seq_id': seq_id
        })
        seq_id += 1
        
        current_node = edge['node_b']
        
        # Trace the path forward
        while True:
            # Find next edge connected to current node
            next_edge_idx = None
            next_is_a = False
            
            for edge_idx, is_a in node_edges[current_node]:
                if edge_idx not in used_edges:
                    next_edge_idx = edge_idx
                    next_is_a = is_a
                    break
            
            if next_edge_idx is None:
                break
            
            # Add next edge
            used_edges.add(next_edge_idx)
            next_edge = edges[next_edge_idx]
            
            # Determine which node is next
            if next_is_a:
                # current_node is node_a, so next is node_b
                next_node = next_edge['node_b']
                next_name = next_edge['name_b']
            else:
                # current_node is node_b, so next is node_a
                next_node = next_edge['node_a']
                next_name = next_edge['name_a']
            
            # Add edge
            route_records.append({
                'name': next_edge['edge_name'],
                'lat': (current_node[0] + next_node[0]) / 2,
                'lon': (current_node[1] + next_node[1]) / 2,
                'type': 'Edge',
                'altitude': next_edge['altitude'],
                'edge_name': next_edge['edge_name'],
                'seq_id': seq_id
            })
            seq_id += 1
            
            # Add node
            route_records.append({
                'name': next_name,
                'lat': next_node[0],
                'lon': next_node[1],
                'type': 'Node',
                'altitude': next_edge['altitude'],
                'edge_name': next_edge['edge_name'],
                'seq_id': seq_id
            })
            seq_id += 1
            
            current_node = next_node
        
        routes.append(route_records)
    
    return routes


def main():
    base_path = Path(r'd:\Lucas\Projeto SAC\Produto 2\REH-SP')
    output_path = base_path / 'output_xml_converted'
    
    # Create output directory if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)
    
    files_to_process = [
        ('CV_REA_XP1_SAO_PAULO.xml', 'REA'),
        ('CV_REH_XP_SAO_PAULO.xml', 'REH')
    ]
    
    route_data = {}  # key: route prefix (REA or REH), value: list of records
    
    for filename, route_name in files_to_process:
        xml_path = base_path / filename
        
        if not xml_path.exists():
            print(f"Warning: {filename} not found")
            continue
        
        print(f"\nProcessing {filename}...")
        records = extract_nodes_and_edges(xml_path, route_name)
        route_data[route_name] = records
    
    # Write separate CSV files for each route
    fieldnames = ['route', 'id', 'name', 'lat', 'lon', 'type', 'altitude', 'height', 'width']
    
    for route_name, records in route_data.items():
        if records:
            output_file = output_path / f'nodes_edges_{route_name.lower()}.csv'
            
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(records)
            
            print(f"Successfully wrote {len(records)} records to {output_file}")
        else:
            print(f"No data for {route_name}")
    
    # Also write a combined file
    all_data = []
    for records in route_data.values():
        all_data.extend(records)
    
    if all_data:
        combined_file = output_path / 'nodes_edges_combined.csv'
        with open(combined_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_data)
        
        print(f"\nSuccessfully wrote {len(all_data)} records to combined file")
    else:
        print("No data to write")


if __name__ == '__main__':
    main()
