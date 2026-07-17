# services/admin.py
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
        # Filter out those that already have a service booking
        already_converted = []
        eligible = []
        for cb in queryset:
            if cb.service_bookings.exists():
                already_converted.append(cb.id)
            else:
                eligible.append(cb)

        if not eligible:
            self.message_user(
                request,
                "All selected cleaning bookings have already been promoted to Service Bookings.",
                level='warning'
            )
            return redirect('admin:services_cleaningbooking_changelist')

        # Prepare IDs for the intermediate view
        ids_string = ','.join(map(str, [cb.id for cb in eligible]))
        
        if already_converted:
            self.message_user(
                request,
                f"Skipped {len(already_converted)} cleaning booking(s) that were already converted. Proceeding with {len(eligible)}.",
                level='warning'
            )
        
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

        # Additional safety: filter out any that might have been converted in the meantime
        eligible = [cb for cb in cleaning_bookings if not cb.service_bookings.exists()]
        if not eligible:
            self.message_user(request, "All selected cleaning bookings have already been converted.", level='warning')
            return redirect('admin:services_cleaningbooking_changelist')

        if request.method == 'POST':
            form = CreateServiceBookingForm(request.POST)
            if form.is_valid():
                service = form.cleaned_data['service']
                provider = form.cleaned_data['provider']

                created_count = 0
                for cb in eligible:
                    # Parse datetime from selected_datetime JSON
                    start_dt = timezone.now()
                    end_dt = timezone.now() + datetime.timedelta(minutes=service.duration_minutes)

                    if isinstance(cb.selected_datetime, dict):
                        booking_date = cb.selected_datetime.get('booking_date')
                        timeslot = cb.selected_datetime.get('timeslot')
                        if booking_date and timeslot:
                            try:
                                date_obj = datetime.datetime.strptime(booking_date, '%Y-%m-%d').date()
                                start_str = timeslot.split(' - ')[0].strip()
                                start_time_obj = datetime.datetime.strptime(start_str, '%H:%M').time()
                                start_dt = timezone.make_aware(datetime.datetime.combine(date_obj, start_time_obj))
                                end_dt = start_dt + datetime.timedelta(minutes=service.duration_minutes)
                            except Exception:
                                pass

                    # Map payment status
                    mapped_payment_status = 'unpaid'
                    if cb.status == 'paid':
                        mapped_payment_status = 'paid_card' if cb.payment_method == 'stripe' else 'paid_cash'

                    # Create ServiceBooking
                    ServiceBooking.objects.create(
                        tenant=cb.tenant,
                        cleaning_booking=cb,
                        service=service,
                        provider=provider,
                        customer_name=cb.customer_name,
                        customer_email=cb.customer_email,
                        phone=cb.phone,
                        property_details=cb.property_details,
                        selected_datetime=cb.selected_datetime,
                        total_price=cb.total,
                        start_time=start_dt,
                        end_time=end_dt,
                        payment_status=mapped_payment_status,
                        status='confirmed',
                    )
                    created_count += 1

                self.message_user(request, f"Successfully created {created_count} Service Booking(s).")
                return redirect('admin:services_servicebooking_changelist')
        else:
            form = CreateServiceBookingForm()

        context = dict(
            self.admin_site.each_context(request),
            title="Promote to Service Booking",
            cleaning_bookings=eligible,  # Only show eligible bookings
            form=form,
        )
        return TemplateResponse(request, 'admin/cleaning_booking_create_service.html', context)


# ==========================================
# ServiceBooking Admin
# ==========================================
@admin.register(ServiceBooking)
class ServiceBookingAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'customer_name', 'customer_email', 'phone',
        'service', 'start_time', 'payment_status', 'status', 'total_price'
    )
    list_filter = ('tenant', 'status', 'payment_status', 'has_complaint', 'rating')
    search_fields = ('customer_name', 'customer_email', 'service__name', 'internal_notes')
    readonly_fields = (
        'cleaning_booking', 'created_at', 'updated_at',
        'stripe_payment_intent_id', 'payment_reference',
        'reschedule_history', 'rescheduled_count'
    )
    fieldsets = (
        ('Booking Source', {
            'fields': ('cleaning_booking',)
        }),
        ('Customer Information', {
            'fields': ('customer_name', 'customer_email', 'phone')
        }),
        ('Property & Datetime', {
            'fields': ('property_details', 'selected_datetime'),
            'classes': ('collapse',)
        }),
        ('Service & Provider', {
            'fields': ('service', 'provider', 'start_time', 'end_time')
        }),
        ('Job Status & Completion', {
            'fields': ('status', 'completed_at', 'actual_duration_minutes', 'customer_notes')
        }),
        ('Payment Details', {
            'fields': ('payment_status', 'payment_date', 'payment_reference', 'total_price', 'discount_applied', 'tax_applied')
        }),
        ('Complaint Tracking', {
            'fields': ('has_complaint', 'complaint_notes', 'complaint_resolved', 'complaint_resolved_at')
        }),
        ('Customer Feedback', {
            'fields': ('rating', 'feedback_text', 'review_request_sent', 'review_requested_at')
        }),
        ('Rescheduling', {
            'fields': ('reschedule_history', 'rescheduled_count')
        }),
        ('Marketing Attribution', {
            'fields': ('utm_source', 'utm_medium', 'utm_campaign')
        }),
        ('Cancellation', {
            'fields': ('cancellation_reason',)
        }),
        ('Internal Notes', {
            'fields': ('internal_notes',)
        }),
        ('System Fields', {
            'fields': ('created_at', 'updated_at', 'stripe_payment_intent_id'),
            'classes': ('collapse',)
        }),
    )
    ordering = ('-start_time',)


# ==========================================
# Register other models (unchanged)
# ==========================================
@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'display_order', 'is_active')
    list_filter = ('tenant', 'is_active')
    search_fields = ('name',)
    ordering = ('tenant', 'display_order', 'name')


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'tenant', 'price_fixed', 'price_per_hour', 'display_order', 'is_addon_only', 'is_active')
    list_filter = ('tenant', 'is_active', 'is_addon_only', 'category', 'requires_assigned_staff')
    search_fields = ('name', 'category__name')
    ordering = ('tenant', 'category__display_order', 'display_order', 'name')


@admin.register(ServiceProvider)
class ServiceProviderAdmin(admin.ModelAdmin):
    list_display = ('user', 'service', 'tenant', 'is_active')
    list_filter = ('tenant', 'is_active')
    search_fields = ('user__email', 'service__name')


@admin.register(BookingSnapshot)
class BookingSnapshotAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'tenant', 'is_final', 'created_at', 'updated_at')
    list_filter = ('tenant', 'is_final', 'created_at')
    search_fields = ('session_id', 'data')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        ('Snapshot Info', {
            'fields': ('session_id', 'tenant', 'is_final')
        }),
        ('Stored Data', {
            'fields': ('data',),
            'classes': ('wide',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(BlockedTime)
class BlockedTimeAdmin(admin.ModelAdmin):
    list_display = ('date', 'timeslot', 'reason')
    list_filter = ('date',)
    search_fields = ('reason', 'timeslot')
