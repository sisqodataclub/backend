# services/utils.py
from .models import Service

def get_cleaning_booking_items(cleaning_booking):
    """
    Given a CleaningBooking instance, return a dict of {service_name: quantity}
    including both numeric service IDs and string keys like 'discount'.
    """
    all_items = {
        **cleaning_booking.quantities,
        **cleaning_booking.carpets,
        **cleaning_booking.appliances
    }

    item_names = {}

    # 1. Handle string keys that are NOT numeric IDs
    for key, qty in all_items.items():
        try:
            int(key)
            # It's a numeric ID, handle below
            continue
        except (ValueError, TypeError):
            # It's a string key (e.g., 'discount', 'furnished_fee')
            try:
                qty_int = int(qty)
                if qty_int > 0:
                    item_names[key] = item_names.get(key, 0) + qty_int
            except (ValueError, TypeError):
                pass

    # 2. Handle numeric IDs
    numeric_ids = [int(k) for k in all_items.keys() if isinstance(k, str) and k.isdigit()]
    if numeric_ids:
        services = Service.objects.filter(id__in=numeric_ids)
        services_map = {s.id: s.name for s in services}

        for sid in numeric_ids:
            name = services_map.get(sid)
            if name:
                qty = all_items.get(str(sid), 1)
                try:
                    qty_int = int(qty)
                except (ValueError, TypeError):
                    qty_int = 1
                if qty_int > 0:
                    item_names[name] = item_names.get(name, 0) + qty_int

    return item_names
