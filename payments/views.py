"""
Payment Views - Secure Stripe Integration
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

from .models import Booking, BookingItem
from .serializers import (
    CreateCheckoutSerializer,
    BookingSerializer,
    CheckoutResponseSerializer
)
from products.models import Product

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


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
        """
        POST /api/payments/bookings/create_checkout/
        
        Create a Stripe Checkout Session
        Frontend sends: product IDs, quantities, customer info
        Backend: Validates prices, creates booking, generates Stripe session
        """
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response(
                {'error': 'Tenant not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate request data
        serializer = CreateCheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        
        try:
            with transaction.atomic():
                # Step 1: Validate products and calculate prices (BACKEND IS SOURCE OF TRUTH)
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
                    
                    # Check stock availability
                    if product.track_inventory and product.stock < item['quantity']:
                        return Response(
                            {'error': f"Insufficient stock for {product.name}"},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                    # Use backend price (NEVER trust frontend)
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
                
                # Step 2: Calculate shipping
                shipping_cost = Decimal('0.00') if subtotal > 250 else Decimal('25.00')
                total = subtotal + shipping_cost
                
                # Step 3: Create Booking with UNPAID status
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
                
                # Step 4: Create BookingItems (snapshot of products)
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
                
                # Step 5: Create Stripe Checkout Session
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
                            'unit_amount': int(item_data['unit_price'] * 100),  # Convert to cents
                        },
                        'quantity': item_data['quantity'],
                    })
                
                # Add shipping as a line item if applicable
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
                
                # Create Stripe session
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
                
                # Step 6: Update booking with Stripe session ID
                booking.stripe_checkout_session_id = checkout_session.id
                booking.save(update_fields=['stripe_checkout_session_id'])
                
                logger.info(f"Created checkout session for booking {booking.id}: {checkout_session.id}")
                
                # Return checkout URL to frontend
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
        """Get client IP address"""
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
    """
    POST /api/payments/webhook/
    
    Stripe Webhook Handler
    Receives payment confirmations from Stripe and updates booking status
    """
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
    
    # Handle the event
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
    """
    Handle successful checkout session
    Update booking status and send confirmation email
    """
    try:
        booking_id = session['metadata'].get('booking_id')
        if not booking_id:
            logger.error("No booking_id in session metadata")
            return
        
        booking = Booking.objects.get(id=booking_id)
        
        # Update booking status
        booking.status = 'PAID'
        booking.stripe_payment_intent_id = session.get('payment_intent', '')
        booking.mark_as_paid()
        
        logger.info(f"Booking {booking.id} marked as PAID")
        
        # Send confirmation email
        _send_confirmation_email(booking)
        
        # Update product stock
        for item in booking.items.all():
            if item.product and item.product.track_inventory:
                item.product.increment_sales(item.quantity)
        
    except Booking.DoesNotExist:
        logger.error(f"Booking not found: {booking_id}")
    except Exception as e:
        logger.error(f"Error handling checkout completion: {str(e)}")


def _handle_payment_failed(payment_intent):
    """Handle failed payment"""
    try:
        # Find booking by payment intent ID
        booking = Booking.objects.filter(
            stripe_payment_intent_id=payment_intent['id']
        ).first()
        
        if booking:
            booking.mark_as_failed()
            logger.info(f"Booking {booking.id} marked as FAILED")
    except Exception as e:
        logger.error(f"Error handling payment failure: {str(e)}")


def _send_confirmation_email(booking):
    """Send order confirmation email"""
    try:
        subject = f"Order Confirmation - Booking #{booking.id}"
        
        # Build email message
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
