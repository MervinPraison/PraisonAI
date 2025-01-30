"""Tools for working with XML files.

Usage:
from praisonaiagents.tools import xml_tools
tree = xml_tools.read_xml("data.xml")

or
from praisonaiagents.tools import read_xml, write_xml, transform_xml
tree = read_xml("data.xml")
"""

import logging
from typing import List, Dict, Union, Optional, Any, Tuple
from importlib import util
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
from io import StringIO
import json

class XMLTools:
    """Tools for working with XML files."""
    
    def __init__(self):
        """Initialize XMLTools."""
        pass

    def read_xml(
        self,
        filepath: str,
        encoding: str = 'utf-8',
        validate_schema: Optional[str] = None,
        parser: str = 'lxml'
    ) -> ET.Element:
        """Read an XML file with optional schema validation.
        
        Args:
            filepath: Path to XML file
            encoding: File encoding
            validate_schema: Optional path to XSD schema file
            parser: XML parser to use ('lxml' or 'etree')
            
        Returns:
            ElementTree root element
        """
        try:
            if parser == 'lxml':
                if util.find_spec('lxml') is None:
                    error_msg = "lxml package is not available. Please install it using: pip install lxml"
                    logging.error(error_msg)
                    return None
                import lxml.etree as lxml_etree
                tree = lxml_etree.parse(filepath)
                root = tree.getroot()
            else:
                tree = ET.parse(filepath)
                root = tree.getroot()

            if validate_schema:
                if util.find_spec('xmlschema') is None:
                    error_msg = "xmlschema package is not available. Please install it using: pip install xmlschema"
                    logging.error(error_msg)
                    return None
                import xmlschema
                schema = xmlschema.XMLSchema(validate_schema)
                if not schema.is_valid(filepath):
                    error_msg = f"XML file does not validate against schema: {schema.validate(filepath)}"
                    logging.error(error_msg)
                    return None

            return root

        except Exception as e:
            error_msg = f"Error reading XML file {filepath}: {str(e)}"
            logging.error(error_msg)
            return None

    def write_xml(
        self,
        root: ET.Element,
        filepath: str,
        encoding: str = 'utf-8',
        pretty: bool = True,
        xml_declaration: bool = True
    ) -> bool:
        """Write XML Element tree to file.
        
        Args:
            root: XML Element tree root
            filepath: Output file path
            encoding: File encoding
            pretty: Format output with proper indentation
            xml_declaration: Include XML declaration
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert to string
            if pretty:
                xml_str = minidom.parseString(
                    ET.tostring(root, encoding='unicode')
                ).toprettyxml(indent='  ')
            else:
                xml_str = ET.tostring(
                    root,
                    encoding='unicode'
                )
            
            # Add declaration if requested
            if xml_declaration:
                if not xml_str.startswith('<?xml'):
                    xml_str = (
                        f'<?xml version="1.0" encoding="{encoding}"?>\n'
                        + xml_str
                    )
            
            # Write to file
            with open(filepath, 'w', encoding=encoding) as f:
                f.write(xml_str)
            
            return True
        except Exception as e:
            error_msg = f"Error writing XML file {filepath}: {str(e)}"
            logging.error(error_msg)
            return False

    def transform_xml(
        self,
        xml_file: str,
        xslt_file: str,
        output_file: str,
        params: Optional[Dict[str, str]] = None
    ) -> bool:
        """Transform XML using XSLT stylesheet.
        
        Args:
            xml_file: Input XML file
            xslt_file: XSLT stylesheet file
            output_file: Output file path
            params: Optional parameters for transformation
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Parse XML and XSLT
            if util.find_spec('lxml') is None:
                error_msg = "lxml package is not available. Please install it using: pip install lxml"
                logging.error(error_msg)
                return False
            import lxml.etree as lxml_etree
            xml_doc = lxml_etree.parse(xml_file)
            xslt_doc = lxml_etree.parse(xslt_file)
            transform = lxml_etree.XSLT(xslt_doc)
            
            # Apply transformation
            if params:
                result = transform(xml_doc, **params)
            else:
                result = transform(xml_doc)
            
            # Write result
            result.write(
                output_file,
                pretty_print=True,
                xml_declaration=True,
                encoding='utf-8'
            )
            
            return True
        except Exception as e:
            error_msg = f"Error transforming XML: {str(e)}"
            logging.error(error_msg)
            return False

    def validate_xml(
        self,
        xml_file: str,
        schema_file: str
    ) -> Tuple[bool, Optional[str]]:
        """Validate XML against XSD schema.
        
        Args:
            xml_file: XML file to validate
            schema_file: XSD schema file
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            if util.find_spec('xmlschema') is None:
                error_msg = "xmlschema package is not available. Please install it using: pip install xmlschema"
                logging.error(error_msg)
                return False, error_msg
            import xmlschema
            schema = xmlschema.XMLSchema(schema_file)
            schema.validate(xml_file)
            return True, None
        except xmlschema.validators.exceptions.XMLSchemaValidationError as e:
            return False, str(e)
        except Exception as e:
            error_msg = f"Error validating XML: {str(e)}"
            logging.error(error_msg)
            return False, error_msg

    def xml_to_dict(
        self,
        root: Union[str, ET.Element],
        preserve_attrs: bool = True
    ) -> Dict[str, Any]:
        """Convert XML to dictionary.
        
        Args:
            root: XML string or Element tree root
            preserve_attrs: Keep XML attributes in result
            
        Returns:
            Dict representation of XML
        """
        try:
            # Parse XML if string
            if isinstance(root, str):
                if root.startswith('<'):
                    root = ET.fromstring(root)
                else:
                    root = ET.parse(root).getroot()
            
            result = {}
            
            # Add attributes if present and requested
            if preserve_attrs and root.attrib:
                result['@attributes'] = dict(root.attrib)
            
            # Add children
            children = list(root)
            if not children:
                text = root.text
                if text is not None and text.strip():
                    result = text.strip()
            else:
                for child in children:
                    child_data = self.xml_to_dict(child, preserve_attrs)
                    if child.tag in result:
                        if not isinstance(result[child.tag], list):
                            result[child.tag] = [result[child.tag]]
                        result[child.tag].append(child_data)
                    else:
                        result[child.tag] = child_data
            
            return result
        except Exception as e:
            error_msg = f"Error converting XML to dict: {str(e)}"
            logging.error(error_msg)
            return {}

    def dict_to_xml(
        self,
        data: Dict[str, Any],
        root_tag: str = 'root'
    ) -> Optional[ET.Element]:
        """Convert dictionary to XML.
        
        Args:
            data: Dictionary to convert
            root_tag: Tag for root element
            
        Returns:
            XML Element tree root
        """
        try:
            def _create_element(
                parent: ET.Element,
                key: str,
                value: Any
            ):
                """Create XML element from key-value pair."""
                if key == '@attributes':
                    for attr_key, attr_val in value.items():
                        parent.set(attr_key, str(attr_val))
                elif isinstance(value, dict):
                    child = ET.SubElement(parent, key)
                    for k, v in value.items():
                        _create_element(child, k, v)
                elif isinstance(value, list):
                    for item in value:
                        child = ET.SubElement(parent, key)
                        if isinstance(item, dict):
                            for k, v in item.items():
                                _create_element(child, k, v)
                        else:
                            child.text = str(item)
                else:
                    child = ET.SubElement(parent, key)
                    child.text = str(value)
            
            root = ET.Element(root_tag)
            for key, value in data.items():
                _create_element(root, key, value)
            
            return root
        except Exception as e:
            error_msg = f"Error converting dict to XML: {str(e)}"
            logging.error(error_msg)
            return None

    def xpath_query(
        self,
        root: Union[str, ET.Element],
        query: str,
        namespaces: Optional[Dict[str, str]] = None
    ) -> List[ET.Element]:
        """Execute XPath query on XML.
        
        Args:
            root: XML string or Element tree root
            query: XPath query string
            namespaces: Optional namespace mappings
            
        Returns:
            List of matching elements
        """
        try:
            # Parse XML if string
            if isinstance(root, str):
                if root.startswith('<'):
                    if util.find_spec('lxml') is None:
                        error_msg = "lxml package is not available. Please install it using: pip install lxml"
                        logging.error(error_msg)
                        return []
                    import lxml.etree as lxml_etree
                    tree = lxml_etree.fromstring(root)
                else:
                    tree = ET.parse(root)
            else:
                if util.find_spec('lxml') is None:
                    error_msg = "lxml package is not available. Please install it using: pip install lxml"
                    logging.error(error_msg)
                    return []
                import lxml.etree as lxml_etree
                tree = lxml_etree.fromstring(
                    ET.tostring(root, encoding='unicode')
                )
            
            # Execute query
            results = tree.xpath(
                query,
                namespaces=namespaces or {}
            )
            
            # Convert results to standard ElementTree elements
            return [
                ET.fromstring(lxml_etree.tostring(elem, encoding='unicode'))
                for elem in results
            ]
        except Exception as e:
            error_msg = f"Error executing XPath query: {str(e)}"
            logging.error(error_msg)
            return []

# Create instance for direct function access
_xml_tools = XMLTools()
read_xml = _xml_tools.read_xml
write_xml = _xml_tools.write_xml
transform_xml = _xml_tools.transform_xml
validate_xml = _xml_tools.validate_xml
xml_to_dict = _xml_tools.xml_to_dict
dict_to_xml = _xml_tools.dict_to_xml
xpath_query = _xml_tools.xpath_query

if __name__ == "__main__":
    print("\n==================================================")
    print("XMLTools Demonstration")
    print("==================================================\n")

    # Create temporary files
    import tempfile
    import os

    temp_file = tempfile.mktemp(suffix='.xml')
    try:
        print("1. Creating XML Document")
        print("------------------------------")
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<bookstore>
    <book category="fiction">
        <title>The Great Gatsby</title>
        <author>F. Scott Fitzgerald</author>
        <year>1925</year>
        <price>10.99</price>
    </book>
    <book category="non-fiction">
        <title>A Brief History of Time</title>
        <author>Stephen Hawking</author>
        <year>1988</year>
        <price>15.99</price>
    </book>
</bookstore>"""
        
        with open(temp_file, 'w') as f:
            f.write(xml_content)
        print("Sample XML file created")
        print()

        print("2. Parsing XML")
        print("------------------------------")
        result = read_xml(temp_file)
        print("XML structure:")
        print(minidom.parseString(ET.tostring(result, encoding='unicode')).toprettyxml(indent='  '))
        print()

        print("3. Querying XML")
        print("------------------------------")
        xpath = "//book[@category='fiction']/title/text()"
        result = xpath_query(result, xpath)
        print(f"Fiction book titles (XPath: {xpath}):")
        for title in result:
            print(title.text)
        print()

        print("4. Validating XML")
        print("------------------------------")
        schema_file = tempfile.mktemp(suffix='.xsd')
        schema_content = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:element name="bookstore">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="book" maxOccurs="unbounded">
                    <xs:complexType>
                        <xs:sequence>
                            <xs:element name="title" type="xs:string"/>
                            <xs:element name="author" type="xs:string"/>
                            <xs:element name="year" type="xs:integer"/>
                            <xs:element name="price" type="xs:decimal"/>
                        </xs:sequence>
                        <xs:attribute name="category" type="xs:string"/>
                    </xs:complexType>
                </xs:element>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>"""
        with open(schema_file, 'w') as f:
            f.write(schema_content)
        result, error = validate_xml(temp_file, schema_file)
        print(f"XML validation result: {result}")
        if error:
            print(f"Error: {error}")
        print()

        print("5. Transforming XML")
        print("------------------------------")
        xslt_content = """<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
    <xsl:template match="/">
        <html>
            <body>
                <h2>Bookstore Inventory</h2>
                <table>
                    <tr>
                        <th>Title</th>
                        <th>Author</th>
                        <th>Price</th>
                    </tr>
                    <xsl:for-each select="bookstore/book">
                        <tr>
                            <td><xsl:value-of select="title"/></td>
                            <td><xsl:value-of select="author"/></td>
                            <td><xsl:value-of select="price"/></td>
                        </tr>
                    </xsl:for-each>
                </table>
            </body>
        </html>
    </xsl:template>
</xsl:stylesheet>"""

        xslt_file = tempfile.mktemp(suffix='.xslt')
        with open(xslt_file, 'w') as f:
            f.write(xslt_content)

        output_file = tempfile.mktemp(suffix='.html')
        result = transform_xml(temp_file, xslt_file, output_file)
        print(f"XML transformation result: {result}")
        if result and os.path.exists(output_file):
            print("\nTransformed HTML content:")
            with open(output_file, 'r') as f:
                print(f.read())

    finally:
        # Clean up temporary files
        for file in [temp_file, schema_file, xslt_file, output_file]:
            if os.path.exists(file):
                os.unlink(file)

    print("\n==================================================")
    print("Demonstration Complete")
    print("==================================================")
