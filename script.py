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

class ConfigGenerator:
    def __init__(self):
        self.template_mapping = {
            'C9300-48UXM': '9300.j2',
            '4506-E': '4500.j2',
            '2960X': '2960x.j2'
        }
        self.checks_path = 'output/checks/campus'

    def get_file_path(self, hostname, type):
        """Get the VLAN file path based on the hostname"""
        if type == 'vlan':
            file_path = os.path.join(self.checks_path, hostname, 'vlan_list.json')
        elif type == 'interface':
            file_path = os.path.join(self.checks_path, hostname, 'interfaces.json')
        if os.path.exists(file_path):
            return file_path
        return None

    @staticmethod
    def trunk_or_not(vlan):
        """Determine if VLAN should be trunked"""
        return vlan['vlan_id'] not in ['666', '1']

    def load_vlans_from_json(self, json_path):
        """Load and process VLAN data from JSON file"""
        try:
            with open(json_path, 'r') as f:
                raw_vlans = json.load(f)
            
            return [{
                'id': vlan['vlan_id'],
                'name': vlan['vlan_name'],
                'trunk': self.trunk_or_not(vlan)
            } for vlan in raw_vlans if vlan['vlan_id'] != '1']
        except Exception as e:
            print(f"Error loading VLAN data: {e}")
            sys.exit(1)

    def get_switches_from_db(self):
        """Get switches configuration from database"""
        conn = None
        try:
            conn = sqlite3.connect('db/db.sqlite')
            cursor = conn.cursor()
            
            cursor.execute('SELECT hostname, invetory_mgmt_ip, model FROM Prechecks')
            
            switches = [{
                'hostname': row[0],
                'mgmt_ip': row[1],
                'model': row[2]
            } for row in cursor.fetchall()]
            
            return {'switches': switches}
        except Exception as e:
            print(f"Database error: {e}")
            sys.exit(1)
        finally:
            if conn:
                conn.close()

    def get_template_path(self, model):
        """Get template path based on switch model"""
        return self.template_mapping.get(model)

    def generate_config(self, template_path, config_data):
        """Generate switch configuration from template"""
        try:
            env = Environment(
                loader=FileSystemLoader(os.path.dirname(template_path))
                #undefined=StrictUndefined
            )
            template = env.get_template(os.path.basename(template_path))
            return template.render(config_data)
        except Exception as e:
            print(f"Error generating configuration: {e}")
            sys.exit(1)

    def save_config(self, config, filename):
        """Save generated configuration to file"""
        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            with open(filename, 'w') as f:
                f.write(config)
            print(f"Configuration saved to {filename}")
        except Exception as e:
            print(f"Error saving configuration: {e}")
            sys.exit(1)

    def find_mgmt_interface(self, switch, json_path):
        """
        Find management interface and subnet mask from interfaces.json.
        
        Args:
            switch (dict): Switch data containing mgmt_ip
            json_path (str): Path to interfaces.json file
            
        Returns:
            dict: Interface info with name and mask, or None if not found
        """
        try:
            # Construct path to interfaces.json for this switch
            interface_file = os.path.join(
                self.checks_path,
                switch['hostname'],
                'interfaces.json'
            )
            
            # Load interfaces data
            with open(interface_file, 'r') as f:
                interfaces = json.load(f)
            
            # Get management IP without CIDR if present
            mgmt_ip = switch['mgmt_ip'].split('/')[0]
            
            # Search through interfaces
            for interface in interfaces:
                if interface.get('ip_address') == mgmt_ip:
                    return {
                        'name': interface['interface'],
                        'mask': interface['prefix_length']                    }
            
            print(f"Warning: No matching interface found for IP {mgmt_ip}")
            return None
            
        except FileNotFoundError:
            print(f"Warning: interfaces.json not found for {switch['hostname']}")
            return None
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON in interfaces file for {switch['hostname']}")
            return None
        except Exception as e:
            print(f"Error finding management interface: {e}")
            return None

def main():
    parser = argparse.ArgumentParser(description='Generate switch configurations')
    parser.add_argument('-o', '--output-dir', required=True, help='Output directory for configurations')
    parser.add_argument('--print', action='store_true', help='Print configurations to console')
    
    args = parser.parse_args()
    generator = ConfigGenerator()
    
    # Load configuration data
    print("Loading configuration files...")
    switches_data = generator.get_switches_from_db()
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Generate configurations for each switch
    for switch in switches_data['switches']:

        vlan_file = generator.get_file_path(switch['hostname'], 'vlan')
        if not vlan_file:
            print(f"Warning: No VLAN file found for {switch['hostname']}")
            continue

        vlans = generator.load_vlans_from_json(vlan_file)

        interface_file = generator.get_file_path(switch['hostname'], 'interface')
        if not vlan_file:
            print(f"Warning: No VLAN file found for {switch['hostname']}")
            continue

        mgmt_interface = generator.find_mgmt_interface(switch,interface_file)
        if mgmt_interface:
            switch.update({
                'mgmt_interface': mgmt_interface['name'],
                'mgmt_subnet': mgmt_interface['mask']
            })

        template_path = generator.get_template_path(switch['model'])
        if not template_path:
            print(f"Warning: No template found for model {switch['model']}")
            continue
            
        config_data = {
            'vlans': vlans,
            **switch
        }
        
        config = generator.generate_config(template_path, config_data)
        output_file = os.path.join(args.output_dir, f"{switch['hostname']}.txt")
        generator.save_config(config, output_file)
        
        if args.print:
            print(f"\nConfiguration for {switch['hostname']}:")
            print(config)
            print("-" * 80)

if __name__ == '__main__':
    main()

