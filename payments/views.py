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

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """List categories (if the package has a Category model)"""
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get']

    def get_queryset(self):
        from sage_invoice.models import Category
        return Category.objects.all()

    def get_serializer_class(self):
        from rest_framework import serializers
        from sage_invoice.models import Category

        class CategorySerializer(serializers.ModelSerializer):
            class Meta:
                model = Category
                fields = ['id', 'name', 'description']
        return CategorySerializer


class ServiceViewSet(viewsets.ReadOnlyModelViewSet):
    """List all services for invoice item selection"""
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get']

    def get_queryset(self):
        from services.models import Service
        return Service.objects.all()

    def get_serializer_class(self):
        from rest_framework import serializers
        from services.models import Service

        class ServiceSerializer(serializers.ModelSerializer):
            class Meta:
                model = Service
                fields = ['id', 'name', 'price', 'description']
        return ServiceSerializer


class CustomerViewSet(viewsets.ModelViewSet):
    """Manage invoice customers"""
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'put', 'patch', 'delete']

    def get_queryset(self):
        from sage_invoice.models import CustomerProfile
        return CustomerProfile.objects.all()

    def get_serializer_class(self):
        from rest_framework import serializers
        from sage_invoice.models import CustomerProfile

        class CustomerProfileSerializer(serializers.ModelSerializer):
            class Meta:
                model = CustomerProfile
                fields = ['id', 'name', 'email', 'phone', 'address']
        return CustomerProfileSerializer


class InvoiceViewSet(viewsets.ModelViewSet):
    """Manage invoices – full CRUD + React Mega Form endpoint"""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from sage_invoice.models import Invoice
        return Invoice.objects.all()

    def get_serializer_class(self):
        from .serializers import InvoiceReadSerializer
        return InvoiceReadSerializer

    # ----------------------------------------------------------------------
    # Standard Full create (supports all fields)
    # ----------------------------------------------------------------------
    def create(self, request, *args, **kwargs):
        from sage_invoice.models import CustomerProfile, Invoice, Category, Item
        from .serializers import InvoiceWriteSerializer, InvoiceReadSerializer

        write_serializer = InvoiceWriteSerializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        data = write_serializer.validated_data

        customer_id = data.get('customer')
        if not customer_id:
            return Response({'customer': 'Customer is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            customer = CustomerProfile.objects.get(id=customer_id)
        except CustomerProfile.DoesNotExist:
            return Response({'customer': 'Customer not found'}, status=status.HTTP_400_BAD_REQUEST)

        category = None
        if data.get('category'):
            try:
                category = Category.objects.get(id=data['category'])
            except Category.DoesNotExist:
                pass

        invoice = Invoice.objects.create(
            customer=customer,
            category=category,
            title=data.get('title', ''),
            slug=data.get('slug', ''),
            tracking_code=data.get('tracking_code', ''),
            issue_date=data.get('issue_date'),
            due_date=data.get('due_date'),
            status=data.get('status', 'draft'),
            is_receipt=data.get('is_receipt', False),
            currency=data.get('currency', 'USD'),
            notes=data.get('notes', ''),
            logo=data.get('logo'),
            signature=data.get('signature'),
            stamp=data.get('stamp'),
            template_choice=data.get('template_choice', ''),
            total_amount=Decimal('0.00'),
        )

        total_amount = Decimal('0.00')
        for item_data in data.get('items', []):
            quantity = Decimal(item_data.get('quantity', 1))
            unit_price = Decimal(item_data.get('unit_price', 0))
            tax_rate = Decimal(item_data.get('tax_rate', 0))
            discount_rate = Decimal(item_data.get('discount_rate', 0))
            line_total = quantity * unit_price * (1 + tax_rate / 100) * (1 - discount_rate / 100)
            total_amount += line_total

            Item.objects.create(
                invoice=invoice,
                description=item_data.get('description', ''),
                quantity=quantity,
                measurement_unit=item_data.get('measurement_unit', ''),
                unit_price=unit_price,
                tax_rate=tax_rate,
                discount_rate=discount_rate,
                total=line_total,
            )

        tax_pct = Decimal(data.get('tax_percentage', 0))
        discount_pct = Decimal(data.get('discount_percentage', 0))
        concession_pct = Decimal(data.get('concession_percentage', 0))
        total_amount = total_amount * (1 + tax_pct / 100) * (1 - discount_pct / 100) * (1 - concession_pct / 100)

        invoice.total_amount = total_amount
        invoice.save()

        out_serializer = InvoiceReadSerializer(invoice)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)

    # ----------------------------------------------------------------------
    # Standard Full update (supports all fields)
    # ----------------------------------------------------------------------
    def update(self, request, *args, **kwargs):
        from sage_invoice.models import CustomerProfile, Invoice, Category, Item
        from .serializers import InvoiceWriteSerializer, InvoiceReadSerializer

        invoice = self.get_object()
        write_serializer = InvoiceWriteSerializer(data=request.data, partial=False)
        write_serializer.is_valid(raise_exception=True)
        data = write_serializer.validated_data

        if data.get('customer') and data['customer'] != invoice.customer.id:
            try:
                invoice.customer = CustomerProfile.objects.get(id=data['customer'])
            except CustomerProfile.DoesNotExist:
                return Response({'customer': 'Customer not found'}, status=status.HTTP_400_BAD_REQUEST)

        if 'category' in data:
            if data['category']:
                try:
                    invoice.category = Category.objects.get(id=data['category'])
                except Category.DoesNotExist:
                    invoice.category = None
            else:
                invoice.category = None

        simple_fields = ['title', 'slug', 'tracking_code', 'issue_date', 'due_date',
                         'status', 'is_receipt', 'currency', 'notes', 'logo',
                         'signature', 'stamp', 'template_choice']
        for field in simple_fields:
            if field in data:
                setattr(invoice, field, data[field])

        try:
            invoice.items.all().delete()
        except AttributeError:
            invoice.invoiceitem_set.all().delete()

        total_amount = Decimal('0.00')
        for item_data in data.get('items', []):
            quantity = Decimal(item_data.get('quantity', 1))
            unit_price = Decimal(item_data.get('unit_price', 0))
            tax_rate = Decimal(item_data.get('tax_rate', 0))
            discount_rate = Decimal(item_data.get('discount_rate', 0))
            line_total = quantity * unit_price * (1 + tax_rate / 100) * (1 - discount_rate / 100)
            total_amount += line_total

            Item.objects.create(
                invoice=invoice,
                description=item_data.get('description', ''),
                quantity=quantity,
                measurement_unit=item_data.get('measurement_unit', ''),
                unit_price=unit_price,
                tax_rate=tax_rate,
                discount_rate=discount_rate,
                total=line_total,
            )

        tax_pct = Decimal(data.get('tax_percentage', 0))
        discount_pct = Decimal(data.get('discount_percentage', 0))
        concession_pct = Decimal(data.get('concession_percentage', 0))
        total_amount = total_amount * (1 + tax_pct / 100) * (1 - discount_pct / 100) * (1 - concession_pct / 100)

        invoice.total_amount = total_amount
        invoice.save()

        out_serializer = InvoiceReadSerializer(invoice)
        return Response(out_serializer.data, status=status.HTTP_200_OK)

    def partial_update(self, request, *args, **kwargs):
        from .serializers import InvoiceWriteSerializer

        invoice = self.get_object()
        write_serializer = InvoiceWriteSerializer(data=request.data, partial=True)
        write_serializer.is_valid(raise_exception=True)
        data = write_serializer.validated_data

        existing_serializer = InvoiceWriteSerializer(invoice)
        merged_data = existing_serializer.data
        for key, value in data.items():
            merged_data[key] = value
        
        request._full_data = merged_data
        return self.update(request, *args, **kwargs)

    # ----------------------------------------------------------------------
    # React Dashboard Mega Form Endpoint (create_with_items)
    # ----------------------------------------------------------------------
    @action(detail=False, methods=['post'])
    def create_with_items(self, request):
        """
        POST /api/payments/invoices/create_with_items/
        Handles the full payload from the React Mega Form.
        """
        from sage_invoice.models import CustomerProfile, Invoice, Item
        from services.models import Service
        from .serializers import InvoiceCreationRequestSerializer, InvoiceReadSerializer

        # 1. Validate incoming Mega Form data
        serializer = InvoiceCreationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        customer_email = data['customer_email']
        customer_name = data.get('customer_name', '')

        # 2. Get or Create Customer
        customer, _ = CustomerProfile.objects.get_or_create(
            email=customer_email,
            defaults={'name': customer_name}
        )

        # 3. Create Invoice Header
        invoice_params = {
            'customer': customer,
            'status': data.get('status', 'draft'),
            'issue_date': data.get('issue_date'),
            'due_date': data.get('due_date'),
        }
        
        # Add the Mega Form optional fields
        if data.get('title'): invoice_params['title'] = data['title']
        if data.get('currency'): invoice_params['currency'] = data['currency']
        if data.get('notes'): invoice_params['notes'] = data['notes']
        if data.get('template_choice'): invoice_params['template_choice'] = data['template_choice']

        # Failsafe creation
        try:
            invoice = Invoice.objects.create(**invoice_params)
        except TypeError:
            invoice = Invoice.objects.create(
                customer=customer, 
                status=data.get('status', 'draft'),
                issue_date=data.get('issue_date'),
                due_date=data.get('due_date')
            )

        # 4. Create Line Items and Calculate Math
        total = Decimal('0.00')
        for item_data in data['items']:
            service_id = item_data.get('service_id')
            if service_id:
                service = Service.objects.get(id=service_id)
                unit_price = Decimal(str(service.price))
                description = service.name
            else:
                unit_price = Decimal(str(item_data.get('unit_price', 0)))
                description = item_data.get('description', '')

            quantity = Decimal(str(item_data.get('quantity', 1)))
            tax_rate = Decimal(str(item_data.get('tax_rate', 0)))
            discount = Decimal(str(item_data.get('discount', 0)))

            # Math Logic
            base_total = quantity * unit_price
            discount_amount = base_total * (discount / Decimal('100'))
            subtotal = base_total - discount_amount
            line_total = subtotal * (Decimal('1') + (tax_rate / Decimal('100')))
            total += line_total

            item_params = {
                'invoice': invoice,
                'description': description,
                'quantity': int(quantity),
                'unit_price': unit_price,
                'tax_rate': tax_rate,
                'total': line_total
            }

            if discount != 0:
                item_params['discount_rate'] = discount
                
            try:
                Item.objects.create(**item_params)
            except TypeError:
                item_params.pop('discount_rate', None)
                Item.objects.create(**item_params)

        # 5. Finalize and Return
        invoice.total_amount = total
        invoice.save()

        out_serializer = InvoiceReadSerializer(invoice)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)

    # ----------------------------------------------------------------------
    # PDF download
    # ----------------------------------------------------------------------
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
        response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'
        return response
