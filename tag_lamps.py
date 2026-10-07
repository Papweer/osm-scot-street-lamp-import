import json
import re
from collections import Counter


INPUT_FOLDER = 'cleaned'
OUTPUT_FOLDER = 'output'

operators = {
    'clackmannanshire': ('Clackmannanshire Council', 'Q28530247'),
    'dundee': ('Dundee City Council', 'Q28528294'),
    'falkirk': ('Falkirk Council', 'Q28530255'),
    'glasgow': ('Glasgow City Council', 'Q130637'),
    'moray': ('Moray Council', 'Q28530260'),
    'orkney': ('Orkney Islands Council', 'Q11994103'),
    'perth-and-kinross': ('Perth and Kinross Council', 'Q7170911'),
    'stirling': ('Stirling Council', 'Q99229589'),
}

# Format for valid refs
refs = {
    'clackmannanshire': ('item_identity_code', r'[A-Z]{1,3}\d{2,4}'),
    'falkirk': ('ID_CODE', r'[A-Z]{1,3}\d{2,4}'),
    'perth-and-kinross': ('Item_Ident', r'[A-Z]\d{4}[A-Za-z]?'),
    'stirling': ('Lighting_ID', r'[A-Z]{3,4}\d{1,2}'),
}

orkneySupports = {
    'Column': 'pole',
    'Floodlight Column': 'pole',
    'Wall Bracket': 'wall_mounted',
    'Wall Light': 'wall',
    'Bulkhead': 'wall',
}

orkneyMaterials = {
    'Steel': 'steel',
    'Galvanised Steel': 'steel',
    'Plastic Coated Steel': 'steel',
    'Aluminium': 'aluminium',
    'Cast iron': 'cast_iron',
}

orkneyLightMethods = {
    'LED': 'led',
    'SON T': 'high_pressure_sodium',
    'SOX': 'low_pressure_sodium',
    'MBFU': 'mercury',
    'Metal Halide': 'metal-halide',
    'Fluorescent': 'fluorescent',
    'Tungsten': 'incandescent',
}

orkneyCouncilDepartments = ['Roads', 'Housing', 'Education', 'Corporate Property', 'Marine Services']

for council, (operator, wikidata) in operators.items():
    with open(f'{INPUT_FOLDER}/{council}.geojson') as geojson:
        data = json.load(geojson)

    # Remove duplicate refs
    if council in refs:
        refField, refPattern = refs[council]
        for feature in data['features']:
            source = feature['properties']
            source[refField] = (source[refField] or '').rstrip('/') # Some refs have a trailing slash
        refCounts = Counter(feature['properties'][refField] for feature in data['features'])

    for feature in data['features']:
        source = feature['properties']

        # Add properties to all lamps
        properties = {
            'highway': 'street_lamp',
            'light_source': 'lantern',
            'operator': operator,
            'operator:wikidata': wikidata,
        }

        # Convert to OSM schema
        if council in refs:
            ref = source[refField]
            if re.fullmatch(refPattern, ref) and refCounts[ref] == 1: # Drops e.g. MISSING, CUT OFF
                properties['ref'] = ref
            if council in ['clackmannanshire', 'falkirk']: # Wall lights are numbered W0001..., underpass lights U0001...
                if ref.startswith('W0'):
                    properties['support'] = 'wall_mounted'
                elif not ref.startswith('U0'):
                    properties['support'] = 'pole'

        match council:
            case 'clackmannanshire':
                if source['mount_height'] != 0: # Some lamps are missing a height
                    properties['height'] = source['mount_height']

                startDate = source['start_date'][:10].replace('/', '-') # 2001/08/01 00:00:00
                if startDate not in ['1900-01-01', '9999-01-01']: # Some lamps are missing a date
                    properties['start_date'] = startDate

            case 'perth-and-kinross':
                if source['Height'] != '1': # 1m is not a valid street lamp height
                    properties['height'] = source['Height']

                # Site_Posit marks the wall mounted lamps, so the rest are columns
                properties['support'] = 'wall_mounted' if source['Site_Posit'] == 'Wall mounted' else 'pole'

            case 'orkney':
                properties['support'] = orkneySupports[source['COLUMN_TYP']]
                if source['COLUMN_TYP'] == 'Floodlight Column':
                    properties['light_source'] = 'floodlight'

                properties['material'] = orkneyMaterials.get(source['COLUMN_MAT'])
                properties['light:method'] = orkneyLightMethods.get(source['LAMP_TYPE_'])

                height = (source['COLUMN_HEI'] or '').lower().removesuffix('m') # Turn 6m into 6
                if re.fullmatch(r'\d+(\.\d+)?', height):
                    properties['height'] = height

                if re.fullmatch(r'(19|20)\d\d', source['ERECTION_Y'] or ''):
                    properties['start_date'] = source['ERECTION_Y']

                if source['BURNING_HO'] == 'All Night':
                    properties['light:lit'] = 'dusk-dawn'

                # e.g. Philips Luma Micro BGP615 DM50
                if source['LUMINAIRE_'] != '?':
                    properties['manufacturer'], properties['model'] = source['LUMINAIRE_'].split(' ', 1)

                if source['RESPONSIBL'] == 'Orkney Housing Association Ltd':
                    properties['operator'] = 'Orkney Housing Association'
                    properties['operator:wikidata'] = 'Q136661725'
                elif source['RESPONSIBL'] not in orkneyCouncilDepartments: # Private, Community Association or unknown
                    properties.pop('operator')
                    properties.pop('operator:wikidata')

        # Drop empty properties
        feature['properties'] = {tag: str(value) for tag, value in properties.items() if value != None}

    # Save final output file
    with open(f'{OUTPUT_FOLDER}/{council}.geojson', 'w') as file:
        json.dump(data, file)
