import csv
import codecs
import pprint
import re
import xml.etree.cElementTree as ET

import cerberus

import schema

# Inputting our XML file, the map data, to the variable OSM_Path
OSM_PATH = "USC-and-Downtown-Los-Angeles.osm"

# These are the names of the CSV files this script will create. 
NODES_PATH = "nodes.csv"
NODE_TAGS_PATH = "nodes_tags.csv"
WAYS_PATH = "ways.csv"
WAY_NODES_PATH = "ways_nodes.csv"
WAY_TAGS_PATH = "ways_tags.csv"

#Recompiler used for renaming street names
street_type_re = re.compile(r'\b\S+\.?$', re.IGNORECASE)

# Regular expressions used in the cleanup process
LOWER_COLON = re.compile(r'^([a-z]|_)+:([a-z]|_)+')
PROBLEMCHARS = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')

SCHEMA = schema.schema

NODE_FIELDS = ['id', 'lat', 'lon', 'user', 'uid', 'version', 'changeset', 'timestamp']
NODE_TAGS_FIELDS = ['id', 'key', 'value', 'type']
WAY_FIELDS = ['id', 'user', 'uid', 'version', 'changeset', 'timestamp']
WAY_TAGS_FIELDS = ['id', 'key', 'value', 'type']
WAY_NODES_FIELDS = ['id', 'node_id', 'position']

# Expected list used for renaming street names
expected = ["Street", "Avenue", "Boulevard", "Drive", "Court", "Place", "Square", "Lane", "Road", 
            "Trail", "Parkway", "Commons", "Way", "Plaza", "Broadway", "Place"]

# Dictionary used for renaming street types
mapping = { "St": "Street",
            "St.": "Street",
           "Str": "Street",
           "Sreet": "Street",
           "Ave": "Avenue",
           "Blvd": "Boulevard",
           "Blvd.": "Boulevard",
           "Bvd": "Boulevard",
           "Pl": "Place"
          }

# Second dictinary used for renaming street names
street_correction = {
    '110402': '9th Street',
    '112': '12th Street',
    '1314': 'South Hill Street',
    '2004': '9th Street',
    '3A': 'Traction Avenue',
    '4045': 'S. Broadway',
    '940': 'S Hill Street',
    'Fl': 'S Grand Avenue',
    'M': 'SE Stark Street',
    '3rd': 'E. 3rd Street',
    'Penthouse': 'West 7th Street',
    'Figueroa': 'Figueroa Street',
    'Pedro': 'S. San Pedro Street',
    'Ducommun': 'Ducommun Street',
    'Mall': '335 E 2nd Street',
    'South': 'South Flower Street',
    'West': '3rd West Street',
}


# Function to update street names
def update_name(name, mapping, street_correction):
    m = street_type_re.search(name) # Recompiler is used to look for a match. Helps us find the street type
    street_type = m.group() # This allows us to work with the street type we grabbed
    if street_type not in expected: # This ensures it only operates update_names on street names that need to be updated
        if street_type not in mapping: 
            name = street_correction[street_type] # This is to correct the ones who whose entire name need to be corrected
        else:
            corrected_street_type = mapping[street_type] # Gets us the corrected street type from the mapping dictionary
            name = name.replace(street_type, corrected_street_type) # Replaces the instance of the incorrected street type 
    return name # Return the corrected street name

# Function used for updating phone numbers

def update_phone_number(phone_number):
    phone_number = re.sub("[-+(). ]", "", phone_number)
    if len(phone_number) > 10:
        phone_number = phone_number[1:]
    phone_number = phone_number[0:3] + "-" + phone_number[3:6] + "-" + phone_number[6:]
    return phone_number

# Function used for updating post codes

def update_post_code(post_code):
    if post_code == 'CA': # This is to fix the post code that just has 'CA' as it's post code. 
        # It is corrected to actual post code.
        post_code = '90057'
    elif post_code == '9006': # This is to fix the post code that just has '9006" as it's post code. 
        #It is corrected to actual post code.
        post_code = '90006'
    else:
        index = post_code.find('9')
        post_code = post_code[index:(index+5)]
    return post_code

def shape_element(element, node_attr_fields=NODE_FIELDS, way_attr_fields=WAY_FIELDS,
                  problem_chars=PROBLEMCHARS, default_tag_type='regular'):
    """Clean and shape node or way XML element to Python dict"""
    
    node_attribs = {}
    way_attribs = {}
    way_nodes = []
    tags = []  # Handle secondary tags the same way for both node and way elements

    # Filling up the node attributes dictionary
    if element.tag == 'node':
        for attrib in node_attr_fields: # Looks at every attribute of the element
            node_attribs[attrib] = element.attrib[attrib]
    
    # Filling up the way attributes dictionary:
    if element.tag == 'way':
        for attrib in way_attr_fields:
            way_attribs[attrib] = element.attrib[attrib]
            
    # Filling up the tags list:
    for tag in element.iter("tag"):
        dic = {}
        dic['id'] = element.attrib['id']
        if ":" in tag.attrib['k']: # Checks if there's a colon in the k value like "addr:street"
            
            splitkey = re.split(":",tag.attrib["k"],1) # This allows us to split on the colon but only the first one
            dic['key'] = splitkey[1] 
            
            if dic['key'] == 'street':
                dic['value'] = update_name(tag.attrib["v"], mapping, street_correction) # Updates street name
                
                
            elif dic['key'] == 'postcode':
                dic['value'] = update_post_code(tag.attrib["v"]) # Updates post code
                
            elif dic['key'] == 'phone':
                dic['value'] = update_phone_number(tag.attrib["v"]) # Updates phone number
            
            else:
                dic['value'] = tag.attrib['v']
            
            dic['type'] = splitkey[0]
            
        else: # If there's no colon in the k value
            dic['key'] = tag.attrib['k']
            
            if dic['key'] == 'street':
                dic['value'] = update_name(tag.attrib["v"], mapping, street_correction) 
                
            elif dic['key'] == 'postcode':
                dic['value'] = update_post_code(tag.attrib["v"])
                
            elif dic['key'] == 'phone':
                dic['value'] = update_phone_number(tag.attrib["v"])
            
            else:
                dic['value'] = tag.attrib['v']
            
            dic['type'] = default_tag_type
            
        tags.append(dic)
        
    # Filling up the way nodes list:
    counter = 0 # This counter will signal the position of the node (nd)
    for tag in element.iter("nd"):
        dicnodes = {}
        dicnodes['id'] = element.attrib['id']
        dicnodes['node_id'] = tag.attrib['ref']
        dicnodes['position'] = counter
        counter += 1
        way_nodes.append(dicnodes)
            
    if element.tag == 'node':
        return {'node': node_attribs, 'node_tags': tags}
    elif element.tag == 'way':
        return {'way': way_attribs, 'way_nodes': way_nodes, 'way_tags': tags}


# ================================================== #
#               Helper Functions                     #
# ================================================== #
def get_element(osm_file, tags=('node', 'way', 'relation')):
    """Yield element if it is the right type of tag"""

    context = ET.iterparse(osm_file, events=('start', 'end'))
    _, root = next(context)
    for event, elem in context:
        if event == 'end' and elem.tag in tags:
            yield elem
            root.clear()


def validate_element(element, validator, schema=SCHEMA):
    """Raise ValidationError if element does not match schema"""
    if validator.validate(element, schema) is not True:
        field, errors = next(validator.errors.iteritems())
        message_string = "\nElement of type '{0}' has the following errors:\n{1}"
        error_string = pprint.pformat(errors)
        
        raise Exception(message_string.format(field, error_string))


class UnicodeDictWriter(csv.DictWriter, object):
    """Extend csv.DictWriter to handle Unicode input"""

    def writerow(self, row):
        super(UnicodeDictWriter, self).writerow({
            k: (v.encode('utf-8') if isinstance(v, unicode) else v) for k, v in row.iteritems()
        })

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


# ================================================== #
#               Main Function                        #
# ================================================== #
def process_map(file_in, validate):
    """Iteratively process each XML element and write to csv(s)"""

    with codecs.open(NODES_PATH, 'w') as nodes_file, \
         codecs.open(NODE_TAGS_PATH, 'w') as nodes_tags_file, \
         codecs.open(WAYS_PATH, 'w') as ways_file, \
         codecs.open(WAY_NODES_PATH, 'w') as way_nodes_file, \
         codecs.open(WAY_TAGS_PATH, 'w') as way_tags_file:

        nodes_writer = UnicodeDictWriter(nodes_file, NODE_FIELDS)
        node_tags_writer = UnicodeDictWriter(nodes_tags_file, NODE_TAGS_FIELDS)
        ways_writer = UnicodeDictWriter(ways_file, WAY_FIELDS)
        way_nodes_writer = UnicodeDictWriter(way_nodes_file, WAY_NODES_FIELDS)
        way_tags_writer = UnicodeDictWriter(way_tags_file, WAY_TAGS_FIELDS)

        nodes_writer.writeheader()
        node_tags_writer.writeheader()
        ways_writer.writeheader()
        way_nodes_writer.writeheader()
        way_tags_writer.writeheader()

        validator = cerberus.Validator()

        for element in get_element(file_in, tags=('node', 'way')):
            el = shape_element(element)
            if el:
                if validate is True:
                    validate_element(el, validator)

                if element.tag == 'node':
                    nodes_writer.writerow(el['node'])
                    node_tags_writer.writerows(el['node_tags'])
                elif element.tag == 'way':
                    ways_writer.writerow(el['way'])
                    way_nodes_writer.writerows(el['way_nodes'])
                    way_tags_writer.writerows(el['way_tags'])


if __name__ == '__main__':
    # Note: Validation is ~ 10X slower. For the project consider using a small
    # sample of the map when validating.
    process_map(OSM_PATH, validate=False)
