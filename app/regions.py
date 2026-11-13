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
