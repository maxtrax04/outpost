"""
Regions for OUTPOST_PROVIDER=auto, worked out from the coordinates alone, with no lookup service
(so the location is never sent anywhere just to find out which country it is in).

The areas are rough rectangles, so places close to a border can land on the wrong side. That is
acceptable here: MET Norway's detailed forecast also covers the areas just outside them, and
OUTPOST_PROVIDER can always name a provider directly.

Uses only the Python standard library.
"""

from typing import List, Tuple

# (south, north, west, east) in decimal degrees
Box = Tuple[float, float, float, float]

# The Nordic countries, where MET Norway's forecast is at its best
NORDIC: List[Box] = [
    (54.5, 71.5, 4.0, 31.6),      # Norway, Sweden, Finland, and Denmark (with the exclusions below)
    (63.2, 66.7, -24.6, -13.4),   # Iceland
    (61.3, 62.5, -7.8, -6.2),     # Faroe Islands
    (74.0, 81.0, 10.0, 35.0),     # Svalbard
    (70.7, 71.3, -9.2, -7.8),     # Jan Mayen
]

# Parts of the first rectangle that belong to other countries
NOT_NORDIC: List[Box] = [
    (54.5, 59.7, 21.0, 31.6),     # Estonia, Latvia, Lithuania, and northwest Russia
    (54.5, 55.4, 15.3, 21.0),     # The Polish coast and Kaliningrad (Bornholm is just west of it)
    (54.5, 61.0, 28.5, 31.6),     # Russia east of southern Finland (Saint Petersburg, Vyborg)
    (64.0, 69.5, 30.3, 31.6),     # Russian Karelia east of northern Finland
]


def _inside(latitude: float, longitude: float, box: Box) -> bool:
    south, north, west, east = box
    return south <= latitude <= north and west <= longitude <= east


def in_nordic_countries(latitude: float, longitude: float) -> bool:
    """True for a location in Norway, Sweden, Finland, Denmark, Iceland, the Faroe Islands, Svalbard, or Jan Mayen."""
    if any(_inside(latitude, longitude, box) for box in NOT_NORDIC):
        return False
    return any(_inside(latitude, longitude, box) for box in NORDIC)


# Mainland Norway as a simplified outline (latitude, longitude), clockwise from the North Sea: along
# the Skagerrak, up the borders with Sweden, Finland, and Russia, and back over the sea. Accurate to
# roughly 10 km along the borders, which is enough to choose an alerts source.
NORWAY_OUTLINE: List[Tuple[float, float]] = [
    (57.6, 4.0), (57.6, 7.6), (58.75, 10.2), (59.0, 10.95),                 # North Sea and Skagerrak
    (59.08, 11.25), (59.12, 11.45), (59.48, 11.73), (59.92, 12.25),         # Svinesund to Magnor
    (60.6, 12.6), (61.3, 12.85), (61.9, 12.4), (62.6, 12.1), (63.3, 12.0),  # Eidskog to Meråker
    (64.0, 13.2), (64.5, 14.0), (65.1, 14.45), (65.75, 14.65), (66.15, 14.75),  # Lierne to Umbukta
    (66.9, 15.6), (67.15, 16.4), (67.9, 17.4), (68.43, 18.12), (68.7, 19.5),     # to Riksgränsen
    (69.06, 20.55), (69.32, 21.27), (68.65, 23.3), (68.85, 24.75),          # Treriksrøysa, Halti, Finnmarksvidda
    (69.42, 25.8), (69.92, 27.0), (70.1, 27.95), (69.7, 29.1),              # Anarjohka and Tana to Neiden
    (69.06, 28.93), (69.45, 30.12), (69.79, 30.82),                         # Pasvik to Grense Jakobselv
    (70.15, 31.4), (71.5, 31.6), (71.5, 4.0),                               # Varanger, Barents and Norwegian Seas
]

# Norway's Arctic islands
NORWAY_ISLANDS: List[Box] = [
    (74.0, 81.0, 10.0, 35.0),     # Svalbard (with Bjørnøya)
    (70.7, 71.3, -9.2, -7.8),     # Jan Mayen
]


def _inside_outline(latitude: float, longitude: float, outline: List[Tuple[float, float]]) -> bool:
    """Ray casting: whether a point is inside a closed outline of (latitude, longitude) points."""
    inside = False
    previous_lat, previous_lon = outline[-1]
    for lat, lon in outline:
        if (lat > latitude) != (previous_lat > latitude):
            crossing = lon + (latitude - lat) * (previous_lon - lon) / (previous_lat - lat)
            if longitude < crossing:
                inside = not inside
        previous_lat, previous_lon = lat, lon
    return inside


def in_norway(latitude: float, longitude: float) -> bool:
    """True for a location in Norway (the mainland, Svalbard, or Jan Mayen), where MET Norway issues warnings."""
    if any(_inside(latitude, longitude, box) for box in NORWAY_ISLANDS):
        return True
    return _inside_outline(latitude, longitude, NORWAY_OUTLINE)
