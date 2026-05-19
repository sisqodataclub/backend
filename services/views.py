# services/views.py – CleaningBookingViewSet (complete)

class CleaningBookingViewSet(ModelViewSet):
    serializer_class = CleaningBookingSerializer
    permission_classes = [permissions.AllowAny]
    queryset = CleaningBooking.objects.all()

    def get_queryset(self):
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            return CleaningBooking.objects.none()
        return CleaningBooking.objects.filter(tenant=self.request.tenant)

    def create(self, request, *args, **kwargs):
        tenant = request.tenant
        if not tenant:
            return Response({"error": "Tenant not identified"}, status=400)

        data = request.data
        session_id = data.get('session_id')

        # 1. IDEMPOTENCY GUARD
        if session_id and CleaningBooking.objects.filter(session_id=session_id, tenant=tenant).exists():
            return Response(
                {"error": "This booking has already been submitted. Please refresh the page."},
                status=409
            )

        def to_int(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0

        # 2. BUILD SERVER-SIDE CART FOR SECURE PRICING
        items = []

        # A. Selected areas (main services)
        for area in data.get('selected_areas', []):
            service = Service.objects.filter(name=area, tenant=tenant, is_active=True).first()
            if service:
                items.append({"service_id": service.id, "quantity": 1})

        # B. Quantities (service IDs and fees)
        for sid, qty in data.get('quantities', {}).items():
            qty = to_int(qty)
            if qty > 0:
                try:
                    service_id = int(sid)
                    if Service.objects.filter(id=service_id, tenant=tenant).exists():
                        items.append({"service_id": service_id, "quantity": qty})
                except ValueError:
                    # It might be a fee key (like 'furnished_fee') – ignore for price calculation
                    pass

        # 3. SECURE PRICE CALCULATION
        subtotal = 0.0
        for item in items:
            service_id = item['service_id']
            quantity = item['quantity']
            try:
                service = Service.objects.get(id=service_id, tenant=tenant, is_active=True)
            except Service.DoesNotExist:
                return Response({"error": f"Service {service_id} not found"}, status=400)

            if service.price_fixed:
                unit_price = float(service.price_fixed)
            elif service.price_per_hour:
                unit_price = float(service.price_per_hour) * (service.duration_minutes / 60)
            else:
                continue
            subtotal += unit_price * quantity

        # 4. FEES (from data, not from quantities)
        fees = 0.0
        furnished = data.get('furnished_status')
        biohazard = data.get('biohazard')
        if furnished == 'furnished':
            fees += 10.0
        if biohazard == 'yes-human':
            fees += 25.0
        elif biohazard == 'yes-animal':
            fees += 15.0
        elif biohazard == 'yes-blood':
            fees += 40.0

        # 5. DISCOUNT
        discount_amount = 0.0
        discount_code = data.get('discount_code')
        if discount_code:
            try:
                from products.models import Discount
                discount = Discount.objects.get(code__iexact=discount_code, tenant=tenant, is_active=True)
                discount_amount = discount.calculate_discount(subtotal + fees)
            except Discount.DoesNotExist:
                pass

        final_total = subtotal + fees - discount_amount
        final_total = max(0.0, final_total)

        if final_total <= 0:
            return Response({"error": "Invalid total amount"}, status=400)

        # 6. STRIPE PAYMENT LINK (if card)
        payment_link = ""
        if data.get('payment_method') == 'card':
            try:
                import stripe
                session = stripe.checkout.Session.create(
                    success_url=data.get('success_url', 'https://core.franciscodes.com/success'),
                    cancel_url=data.get('cancel_url', 'https://core.franciscodes.com/cancel'),
                    payment_method_types=["card"],
                    line_items=[{
                        "price_data": {
                            "currency": "gbp",
                            "unit_amount": int(final_total * 100),
                            "product_data": {"name": "Cleaning Service"},
                        },
                        "quantity": 1,
                    }],
                    mode="payment",
                )
                payment_link = session.url
            except Exception as e:
                return Response({"error": f"Stripe error: {str(e)}"}, status=500)

        # 7. SAVE BOOKING
        booking = CleaningBooking.objects.create(
            tenant=tenant,
            session_id=session_id,
            customer_name=data.get('name', ''),
            customer_email=data.get('email'),
            phone=data.get('phone', ''),
            selected_areas=data.get('selected_areas', []),
            quantities=data.get('quantities', {}),
            carpets=data.get('carpets', {}),
            appliances=data.get('appliances', {}),
            furnished_status=furnished or '',
            parking=data.get('parking', ''),
            biohazard=biohazard or '',
            payment_method=data.get('payment_method', 'unknown'),
            total=final_total,
            paymentlink=payment_link,
        )

        # 8. SEND CONFIRMATION EMAIL (clean version, only from booking.quantities)
        try:
            all_items = booking.quantities.copy()   # only numeric service IDs and fee keys

            # Collect numeric keys (service IDs)
            numeric_ids = []
            for key in all_items.keys():
                try:
                    kid = int(key)
                    if 1 <= kid <= 10000:          # service IDs are typically small
                        numeric_ids.append(kid)
                except (ValueError, TypeError):
                    pass

            # Look up service names using the booking's own tenant
            services_map = {}
            if numeric_ids:
                services = Service.objects.filter(
                    id__in=numeric_ids,
                    tenant=booking.tenant,          # critical: use booking's tenant
                    is_active=True
                )
                services_map = {s.id: s.name for s in services}
                missing = set(numeric_ids) - set(services_map.keys())
                if missing:
                    logger.warning(f"Booking {booking.id}: missing service IDs: {missing}")

            # Build the final item_names dictionary
            item_names = {}

            # Add main selected areas first (these are human-readable strings)
            for area in booking.selected_areas:
                item_names[area] = 1

            # Process all items from quantities
            for key, qty in all_items.items():
                try:
                    qty_int = int(qty)
                except (ValueError, TypeError):
                    continue
                if qty_int <= 0:
                    continue
                # Try to convert key to integer (service ID)
                try:
                    sid = int(key)
                    name = services_map.get(sid)
                    if name:
                        item_names[name] = qty_int
                    else:
                        # Fallback (should not happen if data is correct)
                        item_names[f"Service {key}"] = qty_int
                except (ValueError, TypeError):
                    # Key is already a human-readable name (e.g., "furnished_fee", "discount")
                    item_names[key] = qty_int

            # Inject personal details from the booking model
            item_names["---"] = "---"
            if booking.customer_name:
                item_names["Name"] = booking.customer_name
            if booking.customer_email:
                item_names["Email"] = booking.customer_email
            if booking.phone:
                item_names["Phone"] = booking.phone
            if booking.furnished_status:
                item_names["Furnished Status"] = booking.furnished_status.title()
            if booking.parking:
                item_names["Parking"] = booking.parking.title()
            if booking.biohazard:
                item_names["Biohazard"] = booking.biohazard.title()
            if booking.payment_method:
                item_names["Payment Method"] = booking.payment_method.title()
            if data.get('booking_date'):
                item_names["Booking Date"] = data.get('booking_date')
            if data.get('timeslot'):
                item_names["Timeslot"] = data.get('timeslot')
            if data.get('address'):
                item_names["Address"] = data.get('address')
            if data.get('postcode'):
                item_names["Postcode"] = data.get('postcode')
            if discount_code and discount_amount > 0:
                item_names["Discount Code"] = discount_code

            # Plain text fallback
            plain_text_items = "\n".join([f"- {k}: {v}" for k, v in item_names.items() if k != "---"])
            plain_message = (
                f"Booking Confirmed! 🎉\n\n"
                f"Booking ID: {booking.id}\n\n"
                f"Summary:\n{plain_text_items}\n\n"
                f"Total Quote: £{final_total}\n\n"
                f"Thank you for choosing Ddeep Cleaning Services!"
            )

            # HTML email
            from django.template.loader import render_to_string
            from django.core.mail import send_mail
            from django.conf import settings

            html_message = render_to_string('thankyou.html', {
                'booking_id': booking.id,
                'total_quote': final_total,
                'booking_items': item_names,
            })

            send_mail(
                subject="Booking Confirmation",
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[booking.customer_email, 'francis@dataclubcenter.com'],
                html_message=html_message,
                fail_silently=False,
            )
        except Exception as e:
            logger.warning(f"Email send failed: {e}")

        # 9. RETURN SUCCESS
        return Response({
            "status": "success",
            "booking_id": booking.id,
            "paymentlink": payment_link,
            "total": final_total,
        }, status=201)
