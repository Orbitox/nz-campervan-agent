"""Domain-Specific ADK Tools for the KiwiCamp New Zealand Campervan Agent."""

from app.tools.nz_campervan_tools import (
    ALL_CAMPERVAN_FUNCTION_TOOLS,
    book_paid_holiday_park_site,
    book_paid_holiday_park_site_tool,
    calculate_campervan_route_segment,
    check_december_weather_and_seasonal_hazards,
    fetch_destination_media_gallery,
    generate_interactive_itinerary_website,
    requires_holiday_park_booking_confirmation,
    reserve_cook_strait_campervan_ferry,
    reserve_cook_strait_campervan_ferry_tool,
    search_nz_holiday_parks_and_campsites,
)

__all__ = [
    "ALL_CAMPERVAN_FUNCTION_TOOLS",
    "book_paid_holiday_park_site",
    "book_paid_holiday_park_site_tool",
    "calculate_campervan_route_segment",
    "check_december_weather_and_seasonal_hazards",
    "fetch_destination_media_gallery",
    "generate_interactive_itinerary_website",
    "requires_holiday_park_booking_confirmation",
    "reserve_cook_strait_campervan_ferry",
    "reserve_cook_strait_campervan_ferry_tool",
    "search_nz_holiday_parks_and_campsites",
]
