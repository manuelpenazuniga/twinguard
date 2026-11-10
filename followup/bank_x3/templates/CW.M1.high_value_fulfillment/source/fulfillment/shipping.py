"""Carrier hand-off for released orders."""

SIGNATURE_THRESHOLD_CENTS = 500_000
INSURED_COUNTRIES = {"US", "CA", "GB", "DE", "FR", "NL", "ES", "IT"}


def build_label(request):
    """Label request sent to the carrier for one released order."""
    signature = request.amount_cents >= SIGNATURE_THRESHOLD_CENTS
    return {
        "order_id": request.order_id,
        "ship_to_country": request.ship_to_country,
        "declared_value_cents": request.amount_cents,
        "currency": request.currency,
        "service": "secure_express" if signature else "express",
        "signature_required": signature,
        "insured": request.ship_to_country in INSURED_COUNTRIES,
    }


def dispatch_shipment(request, carrier):
    """Hand the order to ``carrier`` and return its tracking number."""
    tracking = carrier(build_label(request))
    if not tracking:
        raise RuntimeError(f"carrier returned no tracking number for {request.order_id}")
    return str(tracking)
