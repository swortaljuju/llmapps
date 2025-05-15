import requests
import xml.etree.ElementTree as ET
from constants import ( HTTP_HEADER_USER_AGENT)
        
ATOM_TAG_PREFIX = "{http://www.w3.org/2005/Atom}"

def is_valid_rss_type(content_type: str) -> bool:
    """
    Check if the content type is a valid RSS type.
    """
    valid_rss_types = [
        "application/rss+xml",
        "text/xml",
        "application/atom+xml",
        "application/xml",
        "text/html",
    ]
    for valid_type in valid_rss_types:
        if valid_type in content_type:
            return True
    return False

def get_atom_tag(tag: str) -> str:
    """
    Get the full Atom tag name with namespace.
    """
    if tag.startswith(ATOM_TAG_PREFIX):
        return tag
    return f"{ATOM_TAG_PREFIX}{tag}"

def is_valid_rss_feed(feed_url: str) -> bool:
    """
    Check if the given URL is a valid RSS feed URL.
    """
    headers = {
            'User-Agent': HTTP_HEADER_USER_AGENT
        }
    response = requests.get(feed_url, timeout=30, headers=headers)
    content_type = response.headers.get('Content-Type', '')
    if not is_valid_rss_type(content_type):
        return False
    if response.status_code >= 400: 
        return False
    root_doc = ET.fromstring(response.text)
    rss_root = root_doc.find(".//rss")
    if root_doc.tag == "rss":
        return root_doc.get("version") == "2.0"
    elif rss_root is not None:
        return True

    if root_doc.tag == get_atom_tag("feed"):
        return True