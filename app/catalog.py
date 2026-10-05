"""Static reference data for an apartments-only marketplace."""

# Bedroom count -> label. 0 is a studio; 3 means three or more.
APARTMENT_SIZES = {
    0: {"label": "Studio", "icon": "sofa", "blurb": "Compact and private. Rest, shower, work."},
    1: {"label": "1 bedroom", "icon": "bed", "blurb": "A real bedroom plus a living space."},
    2: {"label": "2 bedrooms", "icon": "home", "blurb": "Room for a small group or a family."},
    3: {"label": "3+ bedrooms", "icon": "building", "blurb": "Large flats for gatherings and day events."},
}

AMENITIES = [
    "Wi-Fi", "High-speed Wi-Fi (1 Gbps)", "Air conditioning", "Ceiling fan", "Heating", "Smart TV", "Netflix", "Prime Video", "HBO", "YouTube Premium",
    "Full kitchen", "Kitchenette", "Microwave", "Refrigerator", "Mini fridge", "Coffee maker", "Kettle", "Coffee & tea",
    "Queen bed", "Full bed", "2 Queen beds", "Desk", "Closet", "Private bathroom", "Shower", "Bathtub", "Washer / dryer", "Clothes dryer", "TV",
    "Workspace", "Balcony", "Natural light", "Elevator", "Wheelchair accessible", "Parking", "Parking with electric gate", "Pet friendly", "Doorman",
    "Self check-in", "Bed linens", "Blackout curtains", "Crib", "Gym access", "Pool access", "Private pool", "BBQ grill", "Toiletries included",
    "No deposit", "No guarantor",
]

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def size_label(bedrooms: int) -> str:
    return APARTMENT_SIZES[min(max(int(bedrooms), 0), 3)]["label"]
