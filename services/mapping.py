def map_cleaning_status_to_service_status(cleaning_status):
    """Map cleaning booking status to service booking status."""
    if cleaning_status == 'pending':
        return 'pending'
    # For 'confirmed' or anything else, treat as confirmed
    return 'confirmed'
