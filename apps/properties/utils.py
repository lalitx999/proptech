import re
import urllib.request
import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

# Approximate centroid coordinates for major provinces and tourist areas in Thailand
# Keyed by lowercase terms for robust multilingual matching
DEFAULT_LOCATION_COORDINATES = [
    # Chon Buri / Pattaya / Bang Lamung
    (['ชลบุรี', 'พัทยา', 'บางละมุง', 'ศรีราชา', 'สัตหีบ', 'chon buri', 'chonburi', 'pattaya', 'bang lamung', 'sriracha'], (Decimal('12.927608'), Decimal('100.877081'))),
    # Chiang Mai / Nimman
    (['เชียงใหม่', 'นิมมาน', 'chiang mai', 'chiangmai', 'nimman'], (Decimal('18.788279'), Decimal('98.985303'))),
    # Phuket
    (['ภูเก็ต', 'ป่าตอง', 'phuket', 'patong'], (Decimal('7.880447'), Decimal('98.392250'))),
    # Nonthaburi
    (['นนทบุรี', 'nonthaburi'], (Decimal('13.859108'), Decimal('100.521652'))),
    # Samut Prakan
    (['สมุทรปราการ', 'samut prakan', 'samutprakan'], (Decimal('13.599096'), Decimal('100.599832'))),
    # Pathum Thani
    (['ปทุมธานี', 'pathum thani', 'pathumthani'], (Decimal('14.020839'), Decimal('100.525024'))),
    # Rayong
    (['ระยอง', 'rayong'], (Decimal('12.681466'), Decimal('101.281609'))),
    # Hua Hin / Prachuap
    (['หัวหิน', 'ประจวบคีรีขันธ์', 'hua hin', 'huahin', 'prachuap'], (Decimal('12.568376'), Decimal('99.957687'))),
    # Khon Kaen
    (['ขอนแก่น', 'khon kaen', 'khonkaen'], (Decimal('16.441935'), Decimal('102.835992'))),
    # Nakhon Ratchasima (Korat)
    (['นครราชสีมา', 'โคราช', 'korat', 'nakhon ratchasima'], (Decimal('14.979899'), Decimal('102.097771'))),
    # Bangkok (Default fallback for capital / unspecified)
    (['กรุงเทพมหานคร', 'กรุงเทพ', 'กทม', 'bangkok', 'bkk'], (Decimal('13.756331'), Decimal('100.501765'))),
]

def extract_google_maps_coordinates(url_or_text: str):
    """
    Extracts (lat, lng) Decimal tuple from various Google Maps link formats:
    - Shortened share links: https://maps.app.goo.gl/..., https://goo.gl/maps/...
    - Place URLs: !3d12.9670233!4d100.906461
    - Viewport URLs: @13.7563309,100.5017651,17z/...
    - Query URLs: ?q=13.7563309,100.5017651
    - Direct coordinate input '13.75633, 100.50176'
    """
    if not url_or_text:
        return None, None

    text = str(url_or_text).strip()

    def _parse_and_round(lat_s: str, lng_s: str):
        try:
            return round(Decimal(lat_s), 6), round(Decimal(lng_s), 6)
        except (InvalidOperation, ValueError):
            return None, None

    # Step 1: If shortened Google Maps URL, resolve the redirect target
    if text.startswith('http') and ('maps.app.goo.gl' in text or 'goo.gl/maps' in text or 'g.co' in text):
        try:
            req = urllib.request.Request(
                text,
                headers={'User-Agent': 'curl/7.68.0'}
            )
            opener = urllib.request.build_opener()
            with opener.open(req, timeout=5) as resp:
                resolved_url = resp.geturl()
                if resolved_url and resolved_url != text:
                    text = resolved_url
                else:
                    body = resp.read().decode('utf-8', errors='ignore')
                    text = body
        except Exception as e:
            logger.debug(f"Failed to follow shortened Google Maps URL: {e}")

    # Pattern 1: Place Pin coordinates !3d(lat)!4d(lng) (Most accurate pin location)
    match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', text)
    if match:
        lat, lng = _parse_and_round(match.group(1), match.group(2))
        if lat and lng:
            return lat, lng

    # Pattern 2: Viewport centroid @lat,lng
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', text)
    if match:
        lat, lng = _parse_and_round(match.group(1), match.group(2))
        if lat and lng:
            return lat, lng

    # Pattern 3: Query coordinates ?q=lat,lng or &query=lat,lng or ll=lat,lng
    match = re.search(r'[?&](?:q|query|ll)=(-?\d+\.\d+),(-?\d+\.\d+)', text)
    if match:
        lat, lng = _parse_and_round(match.group(1), match.group(2))
        if lat and lng:
            return lat, lng

    # Pattern 4: Direct coordinate input '13.7563, 100.5018'
    match = re.search(r'^(-?\d+\.\d+)[\s,]+(-?\d+\.\d+)$', text)
    if match:
        lat, lng = _parse_and_round(match.group(1), match.group(2))
        if lat and lng:
            return lat, lng

    return None, None


def get_default_coordinates_for_location(province: str = '', district: str = ''):
    """Fallback coordinates if no map link or GPS provided. Multilingual Thai/English search."""
    search_str = f"{province or ''} {district or ''}".strip().lower()
    for keywords, coords in DEFAULT_LOCATION_COORDINATES:
        for kw in keywords:
            if kw in search_str:
                return coords

    # Default Thailand / Bangkok
    return Decimal('13.756331'), Decimal('100.501765')
