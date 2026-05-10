from datetime import datetime, timedelta
from django.utils import timezone
from .models import Service, ServiceProvider, ServiceBooking
from typing import List, Dict, Optional

def get_available_slots(
    service_id: int,
    date: datetime,
    tenant_id: int,
    provider_id: Optional[int] = None
) -> List[Dict]:
    """
    Returns a list of available time slots for a given service on a specific date.
    """
    service = Service.objects.get(id=service_id, tenant_id=tenant_id)
    duration = service.duration_minutes
    max_per_slot = service.max_clients_per_slot

    # Providers that can do this service
    providers = ServiceProvider.objects.filter(
        service=service, is_active=True, tenant_id=tenant_id
    )
    if provider_id:
        providers = providers.filter(id=provider_id)

    # Define working window (9 AM - 8 PM)
    day_start = datetime(date.year, date.month, date.day, 9, 0, tzinfo=timezone.get_current_timezone())
    day_end = datetime(date.year, date.month, date.day, 20, 0, tzinfo=timezone.get_current_timezone())

    slots = []
    current = day_start
    while current + timedelta(minutes=duration) <= day_end:
        slot_end = current + timedelta(minutes=duration)
        available_providers = []
        for prov in providers:
            day_of_week = current.weekday()
            avail_json = prov.weekly_availability.get(str(day_of_week), [])
            if not any(
                s['start'] <= current.strftime("%H:%M") <= s['end']
                for s in avail_json
            ):
                continue

            # Check overlapping ServiceBookings (was Booking)
            overlapping = ServiceBooking.objects.filter(
                provider=prov,
                start_time__lt=slot_end,
                end_time__gt=current,
                status__in=['confirmed', 'pending', 'in_progress']
            ).count()
            if overlapping < max_per_slot:
                available_providers.append(prov.id)

        if available_providers:
            slots.append({
                'start': current,
                'end': slot_end,
                'provider_ids': available_providers
            })

        current += timedelta(minutes=30)  # slot interval

    return slots
