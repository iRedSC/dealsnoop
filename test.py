import json
import re
from curl_cffi import requests as crequests


def fetch_marketplace_page(url):
    response = crequests.get(url, impersonate="chrome110")
    return response.text


def extract_all_json_data(html):
    all_data = []

    patterns = [
        r'window\.__.{1,50}?\s*=\s*({.+?});',
        r'data-sjs>(.+?)</script>',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, html, re.DOTALL)
        for match in matches:
            try:
                data = json.loads(match)
                all_data.append(("direct", data))
            except json.JSONDecodeError:
                try:
                    data = json.loads(match.replace('\\"', '"'))
                    all_data.append(("decoded", data))
                except:
                    continue

    return all_data


def analyze_data(all_data):
    """Analyze all JSON entries to find listings"""
    for i, (source, data) in enumerate(all_data):
        print(f"\n=== Entry {i+1} ({source}) ===")
        
        if isinstance(data, dict):
            print(f"Keys: {list(data.keys())[:20]}")
            analyze_dict(data, indent=1)
        elif isinstance(data, list):
            print(f"List with {len(data)} items")
            if data:
                print(f"First item type: {type(data[0]).__name__}")


def analyze_dict(obj, indent=0, max_depth=4, max_items=5):
    """Recursively analyze dict structure"""
    if indent > max_depth:
        return
    
    if isinstance(obj, dict):
        for key, value in list(obj.items())[:max_items]:
            prefix = "  " * indent
            if isinstance(value, (dict, list)):
                print(f"{prefix}{key}: {type(value).__name__}")
                analyze_dict(value, indent + 1, max_depth, max_items)
            elif isinstance(value, str) and len(value) > 50:
                print(f"{prefix}{key}: str (len={len(value)})")
            else:
                print(f"{prefix}{key}: {type(value).__name__} = {str(value)[:50]}")


def find_product_listings(all_data):
    """Find actual product listings in the data"""
    for source, data in all_data:
        result = search_for_products(data)
        if result and len(result) > 5:
            print(f"\n✅ Found {len(result)} products in entry")
            return result
    return []


def search_for_products(obj, depth=0, max_depth=5):
    """Search for actual product/listing data"""
    if depth > max_depth:
        return None
    
    if isinstance(obj, dict):
        # Skip navigation/category keys
        skip_keys = ["navigation", "categories", "tabs", "filters", "bucket"]
        for key in skip_keys:
            if key.lower() in obj:
                del obj[key]
        
        for key, value in obj.items():
            if isinstance(value, list) and len(value) > 0:
                # Check if this looks like products
                if is_product_list(value):
                    return value
            result = search_for_products(value, depth + 1, max_depth)
            if result:
                return result
    elif isinstance(obj, list):
        if is_product_list(obj):
            return obj
        for item in obj[:3]:
            result = search_for_products(item, depth + 1, max_depth)
            if result:
                return result
    
    return None


def is_product_list(items):
    """Check if this list contains product listings"""
    if not items or not isinstance(items, list):
        return False
    
    for item in items[:3]:
        if not isinstance(item, dict):
            return False
        
        # Product indicators
        product_keys = ["title", "name", "price", "image", "photo", "location"]
        has_product_keys = sum(1 for k in product_keys if k in item)
        
        # Category indicators (we want to avoid these)
        category_keys = ["category", "icon", "display_name"]
        has_category_keys = sum(1 for k in category_keys if k in item)
        
        if has_product_keys >= 2 and has_category_keys == 0:
            return True
    
    return False


def extract_image(listing):
    """Extract image URL from listing"""
    photo_fields = ["primary_listing_photo", "image", "photo", "thumbnail", "url"]
    for field in photo_fields:
        if field in listing:
            val = listing[field]
            if isinstance(val, str):
                return val
            elif isinstance(val, dict):
                return val.get("uri") or val.get("url") or val.get("image")
    return None


def clean_listing(listing):
    """Clean a single listing"""
    listing_id = listing.get("listing_id") or listing.get("id") or ""
    return {
        "id": listing_id,
        "title": listing.get("title") or listing.get("name"),
        "price": listing.get("price") or listing.get("listing_price"),
        "location": listing.get("location") or listing.get("city"),
        "image_url": extract_image(listing),
        "url": f"https://www.facebook.com/marketplace/item/{listing_id}" if listing_id else None,
    }


def get_marketplace_listings(query, city_code="newyork"):
    """Main function"""
    url = f"https://www.facebook.com/marketplace/search?query={query}"
    html = fetch_marketplace_page(url)
    all_data = extract_all_json_data(html)
    print(all_data)
    
    print(f"Found {len(all_data)} JSON entries")
    
    # Debug: analyze structure
    # analyze_data(all_data)
    
    raw_listings = find_product_listings(all_data)
    return [clean_listing(l) for l in raw_listings if l.get("id")]


if __name__ == "__main__":
    listings = get_marketplace_listings("bike", "newyork")
    print(f"\nFound {len(listings)} product listings:\n")
    for listing in listings[:10]:
        print(f"Title: {listing['title']}")
        print(f"Price: {listing['price']}")
        print(f"URL: {listing['url']}")
        print("---")