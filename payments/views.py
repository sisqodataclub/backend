"""
Payment Views - Secure Stripe Integration & Invoice Management
Backend is the source of truth for all pricing
"""
import logging
import stripe
from decimal import Decimal
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from .models import Booking, BookingItem
from .serializers import (
    CreateCheckoutSerializer,
    BookingSerializer,
    CheckoutResponseSerializer
)
from products.models import Product
from services.models import ServiceBooking

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


# ============================================================================
# E-COMMERCE & STRIPE CHECKOUT
# ============================================================================

class BookingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Booking/Order ViewSet
    Allows users to view their booking history
    """
    serializer_class = BookingSerializer
    permission_classes = [permissions.AllowAny]  # TODO: Change to IsAuthenticated when auth is ready

    def get_queryset(self):
        """Filter bookings by tenant"""
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return Booking.objects.none()

        queryset = Booking.objects.filter(tenant=tenant).prefetch_related('items')

        # Filter by customer email if provided
        email = self.request.query_params.get('email')
        if email:
            queryset = queryset.filter(customer_email=email)

        return queryset

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def create_checkout(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response(
                {'error': 'Tenant not found'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = CreateCheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        try:
            with transaction.atomic():
                items_data = []
                subtotal = Decimal('0.00')

                for item in data['items']:
                    try:
                        product = Product.objects.get(
                            id=item['product_id'],
                            tenant=tenant,
                            is_active=True
                        )
                    except Product.DoesNotExist:
                        return Response(
                            {'error': f"Product {item['product_id']} not found or inactive"},
                            status=status.HTTP_404_NOT_FOUND
                        )

                    if product.track_inventory and product.stock < item['quantity']:
                        return Response(
                            {'error': f"Insufficient stock for {product.name}"},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                    unit_price = product.final_price
                    line_total = unit_price * item['quantity']
                    subtotal += line_total

                    items_data.append({
                        'product': product,
                        'quantity': item['quantity'],
                        'variant': item.get('variant', ''),
                        'unit_price': unit_price,
                        'line_total': line_total,
                    })

                shipping_cost = Decimal('0.00') if subtotal > 250 else Decimal('25.00')
                total = subtotal + shipping_cost

                booking = Booking.objects.create(
                    tenant=tenant,
                    customer_email=data['customer_email'],
                    customer_name=data.get('customer_name', ''),
                    status='UNPAID',
                    subtotal=subtotal,
                    shipping_cost=shipping_cost,
                    total=total,
                    is_gift=data.get('is_gift', False),
                    gift_message=data.get('gift_message', ''),
                    ip_address=self._get_client_ip(request),
                )

                for item_data in items_data:
                    product = item_data['product']
                    BookingItem.objects.create(
                        tenant=tenant,
                        booking=booking,
                        product=product,
                        product_name=product.name,
                        product_sku=product.sku,
                        variant_name=item_data['variant'],
                        unit_price=item_data['unit_price'],
                        quantity=item_data['quantity'],
                        line_total=item_data['line_total'],
                        product_image=product.image_url or '',
                    )

                line_items = []
                for item_data in items_data:
                    product = item_data['product']
                    line_items.append({
                        'price_data': {
                            'currency': settings.ECOMMERCE.get('DEFAULT_CURRENCY', 'usd').lower(),
                            'product_data': {
                                'name': product.name,
                                'description': product.short_description or product.description[:100],
                                'images': [product.image_url] if product.image_url else [],
                            },
                            'unit_amount': int(item_data['unit_price'] * 100),
                        },
                        'quantity': item_data['quantity'],
                    })

                if shipping_cost > 0:
                    line_items.append({
                        'price_data': {
                            'currency': settings.ECOMMERCE.get('DEFAULT_CURRENCY', 'usd').lower(),
                            'product_data': {
                                'name': 'Shipping',
                            },
                            'unit_amount': int(shipping_cost * 100),
                        },
                        'quantity': 1,
                    })

                checkout_session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=line_items,
                    mode='payment',
                    success_url=settings.STRIPE_SUCCESS_URL + f'?session_id={{CHECKOUT_SESSION_ID}}',
                    cancel_url=settings.STRIPE_CANCEL_URL,
                    customer_email=data['customer_email'],
                    metadata={
                        'booking_id': booking.id,
                        'tenant_id': tenant.id,
                    },
                )

                booking.stripe_checkout_session_id = checkout_session.id
                booking.save(update_fields=['stripe_checkout_session_id'])

                logger.info(f"Created checkout session for booking {booking.id}: {checkout_session.id}")

                return Response({
                    'checkout_url': checkout_session.url,
                    'booking_id': booking.id,
                    'session_id': checkout_session.id,
                }, status=status.HTTP_201_CREATED)

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {str(e)}")
            return Response(
                {'error': 'Payment processing error. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"Checkout error: {str(e)}")
            return Response(
                {'error': 'An error occurred. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        logger.error("Invalid webhook payload")
        return Response({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError:
        logger.error("Invalid webhook signature")
        return Response({'error': 'Invalid signature'}, status=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        _handle_checkout_session_completed(session)
    elif event['type'] == 'payment_intent.succeeded':
        payment_intent = event['data']['object']
        logger.info(f"Payment succeeded: {payment_intent['id']}")
    elif event['type'] == 'payment_intent.payment_failed':
        payment_intent = event['data']['object']
        _handle_payment_failed(payment_intent)

    return Response({'status': 'success'}, status=200)


def _handle_checkout_session_completed(session):
    try:
        booking_id = session['metadata'].get('booking_id')
        if not booking_id:
            logger.error("No booking_id in session metadata")
            return

        booking = Booking.objects.get(id=booking_id)
        booking.status = 'PAID'
        booking.stripe_payment_intent_id = session.get('payment_intent', '')
        booking.mark_as_paid()

        logger.info(f"Booking {booking.id} marked as PAID")
        _send_confirmation_email(booking)

        for item in booking.items.all():
            if item.product and item.product.track_inventory:
                item.product.increment_sales(item.quantity)

    except Booking.DoesNotExist:
        logger.error(f"Booking not found: {booking_id}")
    except Exception as e:
        logger.error(f"Error handling checkout completion: {str(e)}")


def _handle_payment_failed(payment_intent):
    try:
        booking = Booking.objects.filter(
            stripe_payment_intent_id=payment_intent['id']
        ).first()

        if booking:
            booking.mark_as_failed()
            logger.info(f"Booking {booking.id} marked as FAILED")
    except Exception as e:
        logger.error(f"Error handling payment failure: {str(e)}")


def _send_confirmation_email(booking):
    try:
        subject = f"Order Confirmation - Booking #{booking.id}"
        items_text = "\n".join([
            f"- {item.product_name} x{item.quantity} - ${item.line_total}"
            for item in booking.items.all()
        ])

        message = f"""
Dear {booking.customer_name or 'Customer'},

Thank you for your order! Your payment has been successfully processed.

Order Details:
--------------
Booking ID: #{booking.id}
Order Date: {booking.created_at.strftime('%B %d, %Y at %I:%M %p')}

Items:
{items_text}

Subtotal: ${booking.subtotal}
Shipping: ${booking.shipping_cost}
Total: ${booking.total}

{"This order includes gift wrapping service." if booking.is_gift else ""}

We'll send you another email when your order ships.

Thank you for shopping with us!

Best regards,
The Team
        """

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[booking.customer_email],
            fail_silently=False,
        )
        logger.info(f"Confirmation email sent to {booking.customer_email}")

    except Exception as e:
        logger.error(f"Error sending confirmation email: {str(e)}")


def create_service_payment_intent(booking: ServiceBooking):
    intent = stripe.PaymentIntent.create(
        amount=int(booking.total_price * 100), 
        currency='usd',
        capture_method='manual',
        metadata={
            'booking_id': booking.id,
            'service_id': booking.service.id,
            'tenant_id': booking.tenant.id,
            'type': 'service_booking'
        },
        description=f"Booking for {booking.service.name} on {booking.start_time.isoformat()}",
    )
    return intent


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def capture_service_payment(request, booking_id):
    booking = get_object_or_404(ServiceBooking, id=booking_id, tenant=request.tenant)
    if booking.status != 'completed':
        return Response({"error": "Service not yet marked as completed"}, status=400)
    intent = stripe.PaymentIntent.capture(booking.stripe_payment_intent_id)
    return Response({"status": "payment captured", "payment_intent_id": intent.id})


# ============================================================================
# INVOICE‑RELATED VIEWSETS (no top‑level imports, lazy loading)
# ============================================================================

# ============================================================================
# INVOICE‑RELATED VIEWSETS (no top‑level imports, lazy loading)
# ============================================================================


# ============================================================================
# INVOICE‑RELATED VIEWSETS (no top‑level imports, lazy loading)
# ============================================================================

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import HttpResponse
from decimal import Decimal
from django.apps import apps
from django.db import transaction
import uuid


def get_invoice_model():
    return apps.get_model('sage_invoice', 'Invoice')


def get_item_model():
    try:
        return apps.get_model('sage_invoice', 'Item')
    except LookupError:
        return apps.get_model('sage_invoice', 'InvoiceItem')


def get_category_model():
    try:
        return apps.get_model('sage_invoice', 'Category')
    except LookupError:
        return None


def get_expense_model():
    return apps.get_model('sage_invoice', 'Expense')


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get']

    def get_queryset(self):
        Category = get_category_model()
        if Category:
            return Category.objects.all()
        return []

    def get_serializer_class(self):
        from rest_framework import serializers
        Category = get_category_model()
        if not Category:
            return serializers.Serializer
        class CategorySerializer(serializers.ModelSerializer):
            class Meta:
                model = Category
                fields = ['id', 'title', 'description']
        return CategorySerializer


class ServiceViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get']

    def get_queryset(self):
        from services.models import Service
        tenant = getattr(self.request, 'tenant', None)
        qs = Service.objects.filter(is_active=True)
        if tenant:
            qs = qs.filter(tenant=tenant)
        return qs

    def list(self, request, *args, **kwargs):
        from decimal import Decimal
        queryset = self.get_queryset()
        data = []
        for service in queryset:
            if service.price_fixed is not None:
                price = Decimal(str(service.price_fixed))
            elif service.price_per_hour is not None:
                hours = Decimal(str(service.duration_minutes)) / Decimal('60')
                price = Decimal(str(service.price_per_hour)) * hours
            else:
                price = Decimal('0')
            data.append({
                'id': service.id,
                'name': service.name,
                'price': price,
                'description': service.description,
                'duration_minutes': service.duration_minutes,
            })
        return Response(data)


class InvoiceViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        Invoice = get_invoice_model()
        return Invoice.objects.all()

    def get_serializer_class(self):
        from .serializers import InvoiceReadSerializer
        return InvoiceReadSerializer

    # Disable default create/update because frontend uses custom endpoint
    def create(self, request, *args, **kwargs):
        return Response({"detail": "Use /create_with_items/ to create invoices"}, status=405)

    def update(self, request, *args, **kwargs):
        return Response({"detail": "Use partial_update or /create_with_items/"}, status=405)

    @action(detail=False, methods=['post'])
    def create_with_items(self, request):
        """
        POST /api/payments/invoices/create_with_items/
        Creates invoice, items, and expense record with full error handling.
        """
        from services.models import Service
        from .serializers import InvoiceCreationRequestSerializer, InvoiceReadSerializer

        Invoice = get_invoice_model()
        ItemModel = get_item_model()
        Expense = get_expense_model()

        # Validate incoming data
        serializer = InvoiceCreationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        data = serializer.validated_data

        # --- 1. Build contacts JSON (sage_invoice format) ---
        contacts = {
            "Contact Info": {
                "email": data['customer_email'],
                "phone": data.get('customer_phone', ''),
            }
        }

        # --- 2. Format notes as JSON array ---
        notes_json = []
        raw_notes = data.get('notes', '')
        if raw_notes:
            notes_json.append({"label": "Additional Notes", "content": raw_notes})

        # --- 3. Ensure unique title (prevent IntegrityError) ---
        title = data.get('title', '').strip()
        if not title:
            title = f"Invoice-{uuid.uuid4().hex[:8]}"
        elif Invoice.objects.filter(title=title).exists():
            title = f"{title}-{uuid.uuid4().hex[:4]}"

        # --- 4. Prepare invoice parameters ---
        invoice_params = {
            'invoice_date': data.get('issue_date'),
            'due_date': data.get('due_date'),
            'status': data.get('status', 'draft'),
            'receipt': data.get('receipt', False),
            'currency': data.get('currency', 'USD'),
            'notes': notes_json,
            'template_choice': data.get('template_choice', 'quotation_1'),
            'customer_name': data.get('customer_name', ''),
            'contacts': contacts,
            'title': title,
        }
        if data.get('category'):
            invoice_params['category_id'] = data['category']

        # --- 5. Atomic transaction (rollback on any error) ---
        try:
            with transaction.atomic():
                # Create invoice
                invoice = Invoice.objects.create(**invoice_params)

                # Create items and compute subtotal
                subtotal = Decimal('0.00')
                for item_data in data['items']:
                    service_id = item_data.get('service_id')
                    if service_id:
                        service = Service.objects.get(id=service_id)
                        if service.price_fixed is not None:
                            unit_price = Decimal(str(service.price_fixed))
                        elif service.price_per_hour is not None:
                            hours = Decimal(str(service.duration_minutes)) / Decimal('60')
                            unit_price = Decimal(str(service.price_per_hour)) * hours
                        else:
                            unit_price = Decimal('0.00')
                        description = service.name
                    else:
                        unit_price = Decimal(str(item_data.get('unit_price', 0)))
                        description = item_data.get('description', '')

                    quantity = Decimal(str(item_data.get('quantity', 1)))
                    tax_rate = Decimal(str(item_data.get('tax_rate', 0)))
                    discount = Decimal(str(item_data.get('discount', 0)))
                    measurement = item_data.get('measurement', '')

                    line_total = quantity * unit_price * (1 + tax_rate/100) * (1 - discount/100)
                    subtotal += line_total

                    # Create item (per‑item tax/discount not stored on item)
                    ItemModel.objects.create(
                        invoice=invoice,
                        description=description,
                        quantity=int(quantity),
                        unit_price=unit_price,
                        measurement=measurement,
                    )

                # --- 6. Create or update Expense (avoid duplicate) ---
                tax_pct = Decimal(str(data.get('tax_percentage', 0)))
                discount_pct = Decimal(str(data.get('discount_percentage', 0)))
                concession_pct = Decimal(str(data.get('concession_percentage', 0)))

                tax_amount = subtotal * (tax_pct / 100)
                discount_amount = subtotal * (discount_pct / 100)
                concession_amount = subtotal * (concession_pct / 100)
                total_amount = subtotal + tax_amount - discount_amount - concession_amount

                expense, created = Expense.objects.get_or_create(
                    invoice=invoice,
                    defaults={
                        'subtotal': subtotal,
                        'tax_percentage': tax_pct,
                        'discount_percentage': discount_pct,
                        'concession_percentage': concession_pct,
                        'tax_amount': tax_amount,
                        'discount_amount': discount_amount,
                        'concession_amount': concession_amount,
                        'total_amount': total_amount,
                    }
                )
                if not created:
                    # Update existing expense (in case of retry)
                    expense.subtotal = subtotal
                    expense.tax_percentage = tax_pct
                    expense.discount_percentage = discount_pct
                    expense.concession_percentage = concession_pct
                    expense.tax_amount = tax_amount
                    expense.discount_amount = discount_amount
                    expense.concession_amount = concession_amount
                    expense.total_amount = total_amount
                    expense.save()

                out_serializer = InvoiceReadSerializer(invoice)
                return Response(out_serializer.data, status=201)

        except Exception as e:
            # Any other error (database, validation, etc.) returns 400
            return Response({'error': str(e)}, status=400)

    @action(detail=True, methods=['get'], url_path='pdf')
    def download_pdf(self, request, pk=None):
        from django.template.loader import render_to_string
        from weasyprint import HTML

        invoice = self.get_object()
        try:
            pdf = invoice.generate_pdf()
            response = HttpResponse(pdf, content_type='application/pdf')
        except AttributeError:
            html_string = render_to_string('invoice_pdf.html', {'invoice': invoice})
            html = HTML(string=html_string)
            pdf = html.write_pdf()
            response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.id}.pdf"'
        return response
