"""Strict Pydantic v2 JSON Schemas for Tools and Structured Agent Outputs (Criterion 1.3).

Defines explicit, strongly-typed Pydantic `BaseModel` schemas with field descriptions,
numeric bounds, enum constraints, and JSON Schema export (`model_json_schema()`) used
to validate all tool arguments, tool return payloads, and structured LLM outputs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

try:
    from pydantic import BaseModel, ConfigDict, Field, field_validator
except ImportError:  # pragma: no cover - lightweight stdlib fallback for sandboxed Python
    class _FieldInfo:
        def __init__(self, default: Any = None, **kwargs: Any) -> None:
            self.default = default
            self.default_factory = kwargs.get("default_factory")
            self.metadata = kwargs

    def Field(default: Any = None, **kwargs: Any) -> Any:  # type: ignore[misc]
        return _FieldInfo(default, **kwargs)

    def ConfigDict(**kwargs: Any) -> Dict[str, Any]:  # type: ignore[misc]
        return kwargs

    def field_validator(*args: Any, **kwargs: Any) -> Any:  # type: ignore[misc]
        def _decorator(fn: Any) -> Any:
            return fn
        return _decorator

    class BaseModel:  # type: ignore[no-redef]
        """Stdlib fallback mimicking Pydantic v2 BaseModel when running without PyPI."""

        def __init__(self, **kwargs: Any) -> None:
            annotations = {}
            for cls in reversed(self.__class__.__mro__):
                annotations.update(getattr(cls, "__annotations__", {}))
            for name in annotations:
                attr_val = getattr(self.__class__, name, None)
                if name in kwargs:
                    val = kwargs[name]
                elif isinstance(attr_val, _FieldInfo):
                    if attr_val.default_factory is not None:
                        val = attr_val.default_factory()
                    else:
                        val = attr_val.default
                else:
                    val = attr_val
                setattr(self, name, val)
            for k, v in kwargs.items():
                if not hasattr(self, k):
                    setattr(self, k, v)

        def model_dump(self) -> Dict[str, Any]:
            def _convert(obj: Any) -> Any:
                if isinstance(obj, BaseModel):
                    return obj.model_dump()
                if isinstance(obj, list):
                    return [_convert(i) for i in obj]
                if isinstance(obj, dict):
                    return {k: _convert(v) for k, v in obj.items()}
                return obj

            return {k: _convert(v) for k, v in self.__dict__.items()}

        @classmethod
        def model_json_schema(cls) -> Dict[str, Any]:
            props: Dict[str, Any] = {}
            required: List[str] = []
            annotations = getattr(cls, "__annotations__", {})
            for name, typ in annotations.items():
                attr_val = getattr(cls, name, None)
                desc = ""
                if isinstance(attr_val, _FieldInfo):
                    desc = attr_val.metadata.get("description", "")
                    if attr_val.default is None and attr_val.default_factory is None:
                        required.append(name)
                props[name] = {"type": str(typ), "description": desc}
            return {
                "title": cls.__name__,
                "type": "object",
                "properties": props,
                "required": required,
            }


class RouteSegmentInput(BaseModel):
    """Input schema for `calculate_campervan_route_segment`."""

    model_config = ConfigDict(extra="forbid")

    origin: str = Field(
        ...,
        min_length=2,
        description="Starting town or landmark in New Zealand (e.g., 'Auckland', 'Cape Reinga').",
    )
    destination: str = Field(
        ...,
        min_length=2,
        description="Destination town or landmark in New Zealand (e.g., 'Paihia (Bay of Islands)').",
    )
    campervan_length_meters: float = Field(
        default=7.2,
        ge=4.5,
        le=9.5,
        description="Total length of the campervan in meters (standard 4-berth is 7.2m).",
    )
    max_safe_daily_driving_hours: float = Field(
        default=4.5,
        ge=1.0,
        le=6.0,
        description="Maximum recommended daily driving hours on winding NZ highways.",
    )


class RouteSegmentOutput(BaseModel):
    """Output schema for `calculate_campervan_route_segment`."""

    status: Literal["success", "error"] = Field(
        ..., description="Execution status of the route calculation."
    )
    origin: str = Field(..., description="Normalized origin location name.")
    destination: str = Field(..., description="Normalized destination location name.")
    distance_km: int = Field(
        default=0, ge=0, description="Driving distance in kilometers."
    )
    estimated_campervan_drive_hours: float = Field(
        default=0.0,
        ge=0.0,
        description="Campervan-adjusted driving duration in hours (includes winding road buffer).",
    )
    state_highways: List[str] = Field(
        default_factory=list,
        description="Primary New Zealand State Highways traversed (e.g., ['SH1', 'SH10']).",
    )
    scenic_waypoints: List[str] = Field(
        default_factory=list,
        description="Recommended stops, viewpoints, and rest areas along the route.",
    )
    road_safety_advisories: List[str] = Field(
        default_factory=list,
        description="Campervan-specific road advisories (one-lane bridges, alpine passes, gravel prohibitions).",
    )
    error_code: Optional[str] = Field(
        default=None, description="Machine-readable error code if status == 'error'."
    )
    recovery_instructions: Optional[str] = Field(
        default=None,
        description="Actionable instructions guiding the LLM on how to recover from an error.",
    )


class CampsiteSearchInput(BaseModel):
    """Input schema for `search_nz_holiday_parks_and_campsites`."""

    model_config = ConfigDict(extra="forbid")

    region_or_town: str = Field(
        ...,
        min_length=2,
        description="Target New Zealand region, town, or national park (e.g., 'Cape Reinga', 'Milford Sound').",
    )
    camping_style: Literal["all", "doc_campsite", "holiday_park", "freedom_camping"] = (
        Field(
            default="all",
            description="Preferred overnight campervan accommodation category.",
        )
    )
    requires_powered_site: bool = Field(
        default=False,
        description="Whether 240V mains power hookup is required for the campervan.",
    )
    self_contained_certified: bool = Field(
        default=True,
        description="Whether the campervan holds a NZ Green Self-Containment Warrant.",
    )


class CampsiteOption(BaseModel):
    """Schema for an individual New Zealand campsite or holiday park."""

    name: str = Field(..., description="Official campsite or holiday park name.")
    category: Literal["doc_campsite", "holiday_park", "freedom_camping"] = Field(
        ..., description="Classification of the campsite."
    )
    region: str = Field(..., description="New Zealand region or town.")
    powered_site_available: bool = Field(
        ..., description="Whether powered campervan bays are available."
    )
    nightly_rate_nzd: float = Field(
        ..., ge=0.0, description="Approximate December peak rate in NZD for 2 adults."
    )
    amenities: List[str] = Field(
        default_factory=list,
        description="On-site campervan facilities (dump station, potable water, hot showers, kitchen).",
    )
    booking_advice_december: str = Field(
        ...,
        description="December peak summer booking lead-time and availability notes.",
    )


class CampsiteSearchOutput(BaseModel):
    """Output schema for `search_nz_holiday_parks_and_campsites`."""

    status: Literal["success", "error"] = Field(
        ..., description="Search execution status."
    )
    region_queried: str = Field(..., description="Region or town searched.")
    campsites: List[CampsiteOption] = Field(
        default_factory=list, description="Matching campsites and holiday parks."
    )
    freedom_camping_bylaw_note: str = Field(
        default="",
        description="Local council freedom camping rules for self-contained vehicles.",
    )
    error_code: Optional[str] = Field(default=None)
    recovery_instructions: Optional[str] = Field(default=None)


class WeatherCheckInput(BaseModel):
    """Input schema for `check_december_weather_and_seasonal_hazards`."""

    model_config = ConfigDict(extra="forbid")

    region_or_landmark: str = Field(
        ...,
        min_length=2,
        description="New Zealand region or destination to check December climate for.",
    )
    day_of_month: int = Field(
        default=15,
        ge=1,
        le=31,
        description="Day in December (1-31) for sunrise/sunset and seasonal conditions.",
    )


class WeatherCheckOutput(BaseModel):
    """Output schema for `check_december_weather_and_seasonal_hazards`."""

    status: Literal["success", "error"] = Field(..., description="Execution status.")
    region: str = Field(..., description="Normalized New Zealand region.")
    season: str = Field(
        default="December (Early Austral Summer)",
        description="New Zealand season description.",
    )
    avg_high_temp_c: float = Field(
        default=21.0, description="Average daytime high temperature in Celsius."
    )
    avg_low_temp_c: float = Field(
        default=11.0, description="Average overnight low temperature in Celsius."
    )
    daylight_hours: float = Field(
        default=15.2, description="Total daily sunlight hours in December."
    )
    uv_index_warning: str = Field(
        default="Extreme (UV Index 11+): Apply SPF50+ reef-safe sunscreen every 2 hours.",
        description="New Zealand ozone/UV protection advisory.",
    )
    seasonal_highlights: List[str] = Field(
        default_factory=list,
        description="December-specific flora, wildlife, and seasonal phenomena (e.g., Pohutukawa blooms, Lupins).",
    )
    campervan_weather_hazards: List[str] = Field(
        default_factory=list,
        description="Wind, sandfly, alpine pass, or coastal tide hazards to prepare for.",
    )
    error_code: Optional[str] = Field(default=None)
    recovery_instructions: Optional[str] = Field(default=None)


class MediaPhotoItem(BaseModel):
    """Curated high-resolution photograph metadata."""

    title: str = Field(..., description="Caption/title of the landmark photo.")
    url: str = Field(..., description="High-resolution image URL.")
    credit: str = Field(..., description="Photographer or Wikimedia/Unsplash attribution.")
    location_tag: str = Field(..., description="Landmark or geographic location tag.")


class MediaVideoItem(BaseModel):
    """Curated YouTube video walkthrough or aerial drone tour metadata."""

    title: str = Field(..., description="Video title.")
    youtube_id: str = Field(..., description="11-character YouTube video identifier.")
    embed_url: str = Field(..., description="YouTube nocookie embed URL.")
    watch_url: str = Field(..., description="Direct YouTube watch URL.")
    duration_label: str = Field(..., description="Approximate video duration label.")


class MediaGalleryInput(BaseModel):
    """Input schema for `fetch_destination_media_gallery`."""

    model_config = ConfigDict(extra="forbid")

    day_number: Optional[int] = Field(
        default=None,
        ge=1,
        le=28,
        description="Optional itinerary day number (1-28) to fetch media for.",
    )
    destination_query: Optional[str] = Field(
        default=None,
        description="Destination or landmark name (e.g., 'Cape Reinga', 'Milford Sound', 'Slope Point').",
    )


class MediaGalleryOutput(BaseModel):
    """Output schema for `fetch_destination_media_gallery`."""

    status: Literal["success", "error"] = Field(..., description="Execution status.")
    destination: str = Field(..., description="Matched destination or day title.")
    day_number: int = Field(default=1, description="Associated itinerary day (1-28).")
    photos: List[MediaPhotoItem] = Field(
        default_factory=list, description="Verified high-resolution photographs."
    )
    videos: List[MediaVideoItem] = Field(
        default_factory=list, description="Curated YouTube video embeds."
    )
    error_code: Optional[str] = Field(default=None)
    recovery_instructions: Optional[str] = Field(default=None)


class FerryReservationInput(BaseModel):
    """Input schema for `reserve_cook_strait_campervan_ferry` (HITL tool)."""

    model_config = ConfigDict(extra="forbid")

    operator: Literal["Interislander", "BlueBridge"] = Field(
        default="Interislander",
        description="Cook Strait ferry operator between Wellington and Picton.",
    )
    sailing_date_iso: str = Field(
        ...,
        description="December sailing date in YYYY-MM-DD format (e.g., '2025-12-13').",
    )
    departure_port: Literal["Wellington", "Picton"] = Field(
        default="Wellington",
        description="Departure port for the Cook Strait crossing.",
    )
    campervan_length_meters: float = Field(
        default=7.2,
        ge=4.5,
        le=9.5,
        description="Total campervan length in meters including bike racks.",
    )
    passengers_adults: int = Field(
        default=2, ge=1, le=6, description="Number of adult passengers."
    )
    fare_Flexibility: Literal["flexible_refundable", "saver_non_refundable"] = Field(
        default="flexible_refundable",
        description="Ticket flexibility tier.",
    )


class FerryReservationOutput(BaseModel):
    """Output schema for `reserve_cook_strait_campervan_ferry`."""

    status: Literal["confirmed", "pending_human_confirmation", "error"] = Field(
        ..., description="Reservation status."
    )
    booking_reference: str = Field(..., description="Ferry reservation code.")
    operator: str = Field(..., description="Selected ferry operator.")
    route: str = Field(..., description="Port-to-port crossing description.")
    sailing_date_iso: str = Field(..., description="Confirmed sailing date.")
    total_cost_nzd: float = Field(..., description="Total fare in NZD.")
    lpg_gas_safety_reminder: str = Field(
        ...,
        description="Mandatory maritime requirement to shut off campervan LPG gas cylinders before boarding.",
    )
    error_code: Optional[str] = Field(default=None)
    recovery_instructions: Optional[str] = Field(default=None)


class HolidayParkBookingInput(BaseModel):
    """Input schema for `book_paid_holiday_park_site` (HITL tool)."""

    model_config = ConfigDict(extra="forbid")

    park_name: str = Field(
        ..., min_length=3, description="Name of the Holiday Park or DOC campsite."
    )
    check_in_date_iso: str = Field(
        ..., description="Check-in date in YYYY-MM-DD format (e.g., '2025-12-21')."
    )
    nights: int = Field(default=1, ge=1, le=7, description="Number of nights.")
    powered_site: bool = Field(
        default=True, description="Whether to book a 240V powered campervan site."
    )
    estimated_total_nzd: float = Field(
        default=85.0, ge=0.0, description="Estimated total booking price in NZD."
    )


class HolidayParkBookingOutput(BaseModel):
    """Output schema for `book_paid_holiday_park_site`."""

    status: Literal["confirmed", "pending_human_confirmation", "error"] = Field(
        ..., description="Booking execution status."
    )
    reservation_id: str = Field(..., description="Holiday park reservation ID.")
    park_name: str = Field(..., description="Booked holiday park name.")
    check_in_date_iso: str = Field(..., description="Check-in date.")
    nights: int = Field(..., description="Number of nights booked.")
    total_charged_nzd: float = Field(..., description="Total cost in NZD.")
    error_code: Optional[str] = Field(default=None)
    recovery_instructions: Optional[str] = Field(default=None)


class WebsiteGenerationInput(BaseModel):
    """Input schema for `generate_interactive_itinerary_website`."""

    model_config = ConfigDict(extra="forbid")

    output_directory: str = Field(
        default="web",
        description="Relative or absolute directory where the website assets will be written.",
    )
    itinerary_title: str = Field(
        default="KiwiCamp: 28-Day New Zealand December Campervan Odyssey",
        description="Headline title displayed on the generated interactive website.",
    )
    include_a2ui_cards: bool = Field(
        default=True,
        description="Whether to generate A2UI v0.9 interactive card payloads alongside HTML/JS.",
    )


class WebsiteGenerationOutput(BaseModel):
    """Output schema for `generate_interactive_itinerary_website`."""

    status: Literal["success", "error"] = Field(..., description="Build status.")
    output_directory: str = Field(..., description="Directory containing generated files.")
    generated_files: List[str] = Field(
        default_factory=list, description="Paths of generated web files."
    )
    total_days_rendered: int = Field(
        default=28, description="Number of itinerary days compiled into the web app."
    )
    total_photos_embedded: int = Field(
        default=0, description="Total curated photos embedded across all days."
    )
    total_videos_embedded: int = Field(
        default=0, description="Total YouTube video tours embedded across all days."
    )
    a2ui_surface_id: str = Field(
        default="nz-campervan-odyssey-v1",
        description="A2UI v0.9 surface identifier.",
    )
    error_code: Optional[str] = Field(default=None)
    recovery_instructions: Optional[str] = Field(default=None)


class DayItineraryPlan(BaseModel):
    """Complete structured schema for a single day of the 28-day NZ Campervan Odyssey."""

    day_number: int = Field(..., ge=1, le=28, description="Day number (1 to 28).")
    date_label: str = Field(..., description="December date label (e.g., 'Dec 1').")
    island: Literal["North Island", "Cook Strait & Marlborough", "South Island"] = Field(
        ..., description="Island or inter-island crossing phase."
    )
    title: str = Field(..., description="Headline title for the day.")
    start_location: str = Field(..., description="Morning departure town/landmark.")
    end_location: str = Field(..., description="Evening overnight town/landmark.")
    latitude: float = Field(..., description="Destination latitude coordinate.")
    longitude: float = Field(..., description="Destination longitude coordinate.")
    drive_distance_km: int = Field(..., ge=0, description="Daily driving distance in km.")
    drive_duration_hours: float = Field(
        ..., ge=0.0, description="Campervan driving time in hours."
    )
    summary: str = Field(..., description="Rich narrative overview of the day's journey.")
    must_do_highlights: List[str] = Field(
        default_factory=list,
        description="Top activities, hikes, and cultural experiences.",
    )
    places_to_check_out: List[str] = Field(
        default_factory=list,
        description="Specific viewpoints, cafes, beaches, and hidden gems.",
    )
    noteworthy_campervan_tips: List[str] = Field(
        default_factory=list,
        description="Crucial campervan parking, road, dump station, and logistics tips.",
    )
    overnight_campsite: CampsiteOption = Field(
        ..., description="Recommended overnight DOC campsite or holiday park."
    )
    december_weather_note: str = Field(
        ..., description="December summer weather, daylight, and seasonal notes."
    )
    photos: List[MediaPhotoItem] = Field(
        default_factory=list, description="High-resolution photos for the day."
    )
    videos: List[MediaVideoItem] = Field(
        default_factory=list, description="YouTube video embeds for the day."
    )


class FullOdysseyItinerary(BaseModel):
    """Complete 28-day New Zealand Campervan Odyssey structured output."""

    itinerary_name: str = Field(
        default="KiwiCamp: 4-Week New Zealand Campervan Odyssey (Auckland -> Cape Reinga -> Slope Point -> Christchurch)"
    )
    travel_month: str = Field(default="December (Austral Summer)")
    total_days: int = Field(default=28)
    arrival_city: str = Field(default="Auckland (AKL)")
    northernmost_point: str = Field(default="Cape Reinga / Te Rerenga Wairua (North Island)")
    southernmost_point: str = Field(default="Bluff & Slope Point (South Island)")
    departure_city: str = Field(default="Christchurch (CHC)")
    total_distance_km: int = Field(default=3945)
    days: List[DayItineraryPlan] = Field(default_factory=list)


class ItineraryQualityEvaluation(BaseModel):
    """Structured output schema for `ItineraryQualityJudgeAgent` (`output_schema`)."""

    grade: Literal["pass", "fail"] = Field(
        ...,
        description="'pass' if all 28 days, northern/southern tips, safe drive limits, and media are complete; otherwise 'fail'.",
    )
    overall_score: int = Field(
        ..., ge=0, le=100, description="Quality score out of 100."
    )
    covers_all_28_days: bool = Field(
        ..., description="True if Days 1 through 28 are all present."
    )
    includes_cape_reinga_and_slope_point: bool = Field(
        ...,
        description="True if both Cape Reinga (North tip) and Bluff/Slope Point (South tip) are included.",
    )
    respects_safe_driving_limits: bool = Field(
        ...,
        description="True if all daily driving segments are safe for a 7.2m campervan.",
    )
    includes_photos_and_videos_every_day: bool = Field(
        ...,
        description="True if every day includes curated photography and YouTube video embeds.",
    )
    critique_summary: str = Field(
        ..., description="Detailed evaluation summary or required fixes."
    )
    improvement_actions: List[str] = Field(
        default_factory=list,
        description="Specific actionable fixes if grade == 'fail'.",
    )
