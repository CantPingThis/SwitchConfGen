import argparse
from jinja2 import Environment, FileSystemLoader, StrictUndefined
import yaml
import json
import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime
from copy import deepcopy

def load_vlans_from_json(json_path):
    """Load VLAN data from JSON file."""
    with open(json_path, 'r') as f:
        raw_vlans = json.load(f)
    
    vlans = []
    for vlan in raw_vlans:
        if vlan == '1':
            pass
        else:
            vlans.append({
                'id': vlan['vlan_id'],
                'name': vlan['vlan_name'],
                'trunk': True
            })
    return vlans

def get_switches_from_db():
    """Get switches from SQL Database"""
    conn = sqlite3.connect('db/db.sqlite')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT hostname, invetory_mgmt_ip, model
        FROM Prechecks
    ''')

    switches = []
    for row in cursor.fetchall():
        switches.append({
            'hostname': row[0],
            'mgmt_ip': row[1],
            'model': row[2]
        })
    conn.close()
    return{'switches': switches}

def load_yaml_file(file_path):
    """Load data from a YAML file."""
    try:
        with open(file_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        sys.exit(1)

def deep_merge(source, destination):
    """
    Deep merge two dictionaries. Source overwrites destination.
    """
    for key, value in source.items():
        if isinstance(value, dict):
            # Get node or create one
            node = destination.setdefault(key, {})
            deep_merge(value, node)
        else:
            destination[key] = value
    return destination

def merge_configurations(base_config, global_config, switch_specific):
    """Merge base, global, and switch-specific configurations."""
    # Create a deep copy of the base config
    config = deepcopy(base_config)
    
    # Merge global settings
    if global_config:
        config = deep_merge(global_config, config)
    
    # Merge switch-specific settings (these take precedence)
    config = deep_merge(switch_specific, config)
    
    # Add generation timestamp
    #config['generation_timestamp'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    
    return config

def get_trunk_vlans(vlans):
    try:
        trunk_vlans = [str(vlan['id']) for vlan in vlans if vlan.get('trunk', True)]
        return ','.join(trunk_vlans)
    except (KeyError, TypeError):
        return ''

def get_trunk_vlans_ap(vlans):
    try:
        trunk_vlans = [str(vlan['id']) for vlan in vlans if vlan.get('ap', True)]
        return ','.join(trunk_vlans)
    except (KeyError, TypeError):
        return ''

def generate_config(template_file, config_data):
    try:
        env = Environment(loader=FileSystemLoader(os.path.dirname(template_file)))

        env.filters['get_trunk_vlans'] = get_trunk_vlans
        env.filters['get_trunk_vlans_ap'] = get_trunk_vlans_ap

        template = env.get_template(os.path.basename(template_file))

        return template.render(config_data)
    except Exception as e:
        print(f"Error generating configuration: {e}")
        sys.exit(1)

def save_config(config, filename):
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, 'w') as f:
            f.write(config)
        print(f"Configuration successfully saved to {filename}")
    except Exception as e:
        print(f"Error saving configuration: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Generate multiple Cisco switch configurations from template')
    parser.add_argument('-t', '--template', required=True, help='Path to the Jinja2 template file')
    parser.add_argument('-v', '--vlans', required=True, help='Path to the vlans file')
    parser.add_argument('-o', '--output-dir', required=True, help='Output directory for the generated configurations')
    parser.add_argument('--print', action='store_true', help='Print the configurations to console')
    
    args = parser.parse_args()

    # Load configuration data
    print("Loading configuration files...")
    #base_config = load_yaml_file(args.base_config)
    vlans = load_vlans_from_json(args.vlans)
    switches_data = get_switches_from_db()
    print(switches_data)
    global_config = switches_data.get('global', {})

    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    for switch in switches_data['switches']:
        
        config_data = {
            'vlans': vlans,
            **switch
        } 
        #print(config_data)       
        # Generate the configuration
        config = generate_config(args.template, config_data)
        
        # Create output filename based on hostname
        output_file = os.path.join(args.output_dir, f"{switch['hostname']}.txt")
        
        # Save the configuration
        save_config(config, output_file)
        
        # Print if requested
        if args.print:
            print(f"\nGenerated Configuration for {switch['hostname']}:")
            print(config)
            print("-" * 80)

if __name__ == "__main__":
    main()

