import datetime
from django.contrib import admin
from django import forms
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone
from .models import (
    ServiceCategory, Service, ServiceProvider, 
    CleaningBooking, ServiceBooking, BookingSnapshot, BlockedTime
)

# ==========================================
# Form for the Intermediate Admin Action
# ==========================================
class CreateServiceBookingForm(forms.Form):
    service = forms.ModelChoiceField(
        queryset=Service.objects.all(), 
        required=True,
        help_text="Select the primary service to assign these bookings to."
    )
    provider = forms.ModelChoiceField(
        queryset=ServiceProvider.objects.all(), 
        required=False, 
        empty_label="Unassigned (Assign later)",
        help_text="Optional: Dispatch to a specific provider immediately."
    )

# ==========================================
# CleaningBooking Admin
# ==========================================
@admin.register(CleaningBooking)
class CleaningBookingAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'customer_name', 'customer_email', 'total', 'status', 'created_at')
    list_filter = ('status', 'payment_method')
    search_fields = ('customer_name', 'customer_email', 'session_id')
    
    actions = ['create_service_booking_action']

    def create_service_booking_action(self, request, queryset):
        """
        Action dropdown: Redirects to our custom intermediate view
        """
        # Convert selected IDs to a comma-separated string
        selected_ids = queryset.values_list('id', flat=True)
        ids_string = ','.join(map(str, selected_ids))
        
        # Redirect to the custom URL we define in get_urls()
        return redirect('admin:create_service_booking_from_cleaning', ids=ids_string)
    
    create_service_booking_action.short_description = "Promote to Service Booking(s)"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'create-service-booking/<str:ids>/', 
                self.admin_site.admin_view(self.create_service_booking_view), 
                name='create_service_booking_from_cleaning'
            ),
        ]
        return custom_urls + urls

    def create_service_booking_view(self, request, ids):
        id_list = [int(x) for x in ids.split(',') if x.isdigit()]
        cleaning_bookings = CleaningBooking.objects.filter(id__in=id_list)

        if not cleaning_bookings.exists():
            self.message_user(request, "No valid cleaning bookings found.", level='error')
            return redirect('admin:services_cleaningbooking_changelist')

        if request.method == 'POST':
            form = CreateServiceBookingForm(request.POST)
            if form.is_valid():
                service = form.cleaned_data['service']
                provider = form.cleaned_data['provider']
                
                created_count = 0
                for cb in cleaning_bookings:
                    # 1. Parse the JSON datetime from the wizard
                    start_dt = timezone.now()
                    end_dt = timezone.now() + datetime.timedelta(minutes=service.duration_minutes)
                    
                    if isinstance(cb.selected_datetime, dict):
                        booking_date = cb.selected_datetime.get('booking_date')
                        timeslot = cb.selected_datetime.get('timeslot')
                        
                        if booking_date and timeslot:
                            try:
                                # Example timeslot: "09:00 - 12:00"
                                date_obj = datetime.datetime.strptime(booking_date, '%Y-%m-%d').date()
                                start_str = timeslot.split(' - ')[0].strip()
                                start_time_obj = datetime.datetime.strptime(start_str, '%H:%M').time()
                                
                                start_dt = timezone.make_aware(datetime.datetime.combine(date_obj, start_time_obj))
                                end_dt = start_dt + datetime.timedelta(minutes=service.duration_minutes)
                            except Exception:
                                pass # Fallback to default timezone.now() if parsing fails

                    # 2. Determine payment status based on wizard data
                    mapped_payment_status = 'unpaid'
                    if cb.status == 'paid':
                        mapped_payment_status = 'paid_card' if cb.payment_method == 'stripe' else 'paid_cash'

                    # 3. Create the ServiceBooking with auto-filled data
                    ServiceBooking.objects.create(
                        tenant=cb.tenant,
                        cleaning_booking=cb,  # Links back to the raw wizard data
                        service=service,
                        provider=provider,
                        customer_name=cb.customer_name,
                        customer_email=cb.customer_email,
                        total_price=cb.total,
                        start_time=start_dt,
                        end_time=end_dt,
                        payment_status=mapped_payment_status,
                        status='confirmed', # Auto-confirm upon promotion
                        # The remaining fields (rating, complaints, UTMs) stay blank per your request
                    )
                    created_count += 1

                self.message_user(request, f"Successfully created {created_count} Service Booking(s).")
                return redirect('admin:services_servicebooking_changelist')
        else:
            form = CreateServiceBookingForm()

        context = dict(
            self.admin_site.each_context(request),
            title="Promote to Service Booking",
            cleaning_bookings=cleaning_bookings,
            form=form,
        )
        # We will create this template next
        return TemplateResponse(request, 'admin/cleaning_booking_create_service.html', context)

# ==========================================
# ServiceBooking Admin
# ==========================================
@admin.register(ServiceBooking)
class ServiceBookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_name', 'service', 'start_time', 'status', 'payment_status')
    list_filter = ('status', 'payment_status', 'has_complaint')
    search_fields = ('customer_name', 'customer_email')
    readonly_fields = ('cleaning_booking', 'created_at', 'updated_at')
