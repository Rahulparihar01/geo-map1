import logging
from typing import Any, Dict, List, Optional
import httpx
from app.core.config import settings
from app.exceptions.places import (
    PlaceDetailNotFoundError,
    GooglePlacesAPIError,
    GooglePlacesTimeoutError,
)
from app.integrations.google_base import GoogleAPIClientBase
from app.schemas.place_details import (
    OpeningHours,
    OpeningHoursPeriod,
    PlaceDetailResult,
    PlacePhoto,
    PlaceReview,
)

logger = logging.getLogger(__name__)
_FIELD_MASK = ",".join(
    [
        "id",
        "displayName",
        "formattedAddress",
        "location",
        "types",
        "primaryType",
        "businessStatus",
        "currentOpeningHours",
        "regularOpeningHours",
        "regularSecondaryOpeningHours",
        "internationalPhoneNumber",
        "nationalPhoneNumber",
        "websiteUri",
        "googleMapsUri",
        "rating",
        "userRatingCount",
        "priceLevel",
        "editorialSummary",
        "photos",
        "reviews",
        "accessibilityOptions",
        "parkingOptions",
        "paymentOptions",
        "dineIn",
        "takeout",
        "delivery",
        "curbsidePickup",
        "reservable",
        "servesBreakfast",
        "servesLunch",
        "servesDinner",
        "servesBeer",
        "servesWine",
        "servesCocktails",
        "outdoorSeating",
        "liveMusic",
        "goodForChildren",
        "goodForGroups",
        "restroom",
        "allowsDogs",
        "utcOffsetMinutes",
        "plusCode",
        "addressComponents",
        "evChargeOptions",
        "subDestinations",
    ]
)


class GooglePlaceDetailsClient(GoogleAPIClientBase):

    def _get_url(self) -> str:
        if not hasattr(self, '_place_id_for_url'):
            raise RuntimeError("_place_id_for_url not set before calling _get_url()")
        return f"{settings.GOOGLE_PLACES_BASE_URL}/places/{self._place_id_for_url}"

    def _get_field_mask(self) -> str:
        return _FIELD_MASK

    def _set_place_for_request(self, place_id: str) -> None:
        self._place_id_for_url = place_id

    async def _do_request(self, payload: Dict, headers: Dict) -> httpx.Response:
        url = self._get_url()
        if self._http_client is not None:
            return await self._http_client.get(url, headers=headers)

        logger.warning(
            "GooglePlaceDetailsClient: No shared HTTP client - creating per-request client. "
            "This should only happen in tests."
        )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.get(url, headers=headers)

    def _parse_opening_hours(
        self, raw: Optional[Dict[str, Any]]
    ) -> Optional[OpeningHours]:
        if not raw:
            return None
        periods: List[OpeningHoursPeriod] = []
        for period in raw.get("periods", []):
            open_p = period.get("open", {})
            close_p = period.get("close", {})
            periods.append(
                OpeningHoursPeriod(
                    open_day=open_p.get("day"),
                    open_hour=open_p.get("hour"),
                    open_minute=open_p.get("minute"),
                    close_day=close_p.get("day"),
                    close_hour=close_p.get("hour"),
                    close_minute=close_p.get("minute"),
                )
            )
        return OpeningHours(
            open_now=raw.get("openNow"),
            weekday_descriptions=raw.get("weekdayDescriptions"),
            periods=periods or None,
        )

    def _parse_photos(
        self, raw_list: Optional[List[Dict[str, Any]]]
    ) -> Optional[List[PlacePhoto]]:
        if not raw_list:
            return None
        return [
            PlacePhoto(
                name=p.get("name"),
                width_px=p.get("widthPx"),
                height_px=p.get("heightPx"),
            )
            for p in raw_list
        ]

    def _parse_reviews(
        self, raw_list: Optional[List[Dict[str, Any]]]
    ) -> Optional[List[PlaceReview]]:
        if not raw_list:
            return None
        results: List[PlaceReview] = []
        for r in raw_list:
            text_obj = r.get("text", {})
            author = r.get("authorAttribution", {})
            results.append(
                PlaceReview(
                    author_name=author.get("displayName"),
                    rating=r.get("rating"),
                    text=(
                        text_obj.get("text") if isinstance(text_obj, dict) else text_obj
                    ),
                    publish_time=r.get("publishTime"),
                    relative_publish_time_description=r.get(
                        "relativePublishTimeDescription"
                    ),
                )
            )
        return results or None

    def _parse_response(
        self, data: Dict[str, Any], requested_place_id: str
    ) -> PlaceDetailResult:
        google_returned_id = data.get("id")
        if google_returned_id and google_returned_id != requested_place_id:
            logger.info(
                "Place ID canonicalised by Google: requested=%s canonical=%s — "
                "storing as requested id to preserve lookup consistency (B15/B-033)",
                requested_place_id,
                google_returned_id,
            )
            editorial_obj = data.get("editorialSummary", {})
            editorial_text = (
                editorial_obj.get("text")
                if isinstance(editorial_obj, dict)
                else editorial_obj
            )
            if editorial_text:
                editorial_text = (
                    f"{editorial_text} [canonical_id: {google_returned_id}]"
                )
            data["editorialSummary"] = (
                {"text": editorial_text} if editorial_text else editorial_obj
            )

        location = data.get("location", {})
        display_name_obj = data.get("displayName", {})
        editorial_obj = data.get("editorialSummary", {})
        accessibility = data.get("accessibilityOptions", {})
        parking = data.get("parkingOptions", {})
        payment = data.get("paymentOptions", {})
        ev = data.get("evChargeOptions", {})

        opening_hours = self._parse_opening_hours(data.get("currentOpeningHours"))
        photos = self._parse_photos(data.get("photos"))
        reviews = self._parse_reviews(data.get("reviews"))

        open_now: Optional[bool] = None
        if opening_hours is not None:
            open_now = opening_hours.open_now

        extended: Dict[str, Any] = {}

        regular_hours = data.get("regularOpeningHours")
        if regular_hours:
            extended["regular_opening_hours"] = regular_hours
        secondary_hours = data.get("regularSecondaryOpeningHours")
        if secondary_hours:
            extended["secondary_opening_hours"] = secondary_hours

        if parking:
            for k, v in parking.items():
                extended[f"parking_{k}"] = v

        if payment:
            for k, v in payment.items():
                extended[f"payment_{k}"] = v

        for flag in ["dineIn", "takeout", "delivery", "curbsidePickup", "reservable"]:
            val = data.get(flag)
            if val is not None:
                extended[flag] = val

        for flag in [
            "servesBreakfast",
            "servesLunch",
            "servesDinner",
            "servesBeer",
            "servesWine",
            "servesCocktails",
        ]:
            val = data.get(flag)
            if val is not None:
                extended[flag] = val

        for flag in [
            "outdoorSeating",
            "liveMusic",
            "goodForChildren",
            "goodForGroups",
            "restroom",
            "allowsDogs",
        ]:
            val = data.get(flag)
            if val is not None:
                extended[flag] = val

        if ev:
            extended["ev_charger_options"] = ev

        utc_offset = data.get("utcOffsetMinutes")
        if utc_offset is not None:
            extended["utc_offset_minutes"] = utc_offset

        plus_code = data.get("plusCode", {})
        if plus_code:
            extended["plus_code"] = plus_code.get("globalCode") or plus_code.get(
                "compoundCode"
            )

        addr_components = data.get("addressComponents", [])
        if addr_components:
            neighborhoods = []
            localities = []
            sublocalities = []
            for comp in addr_components:
                types_list = comp.get("types", [])
                text = comp.get("longText") or ""
                if "neighborhood" in types_list:
                    neighborhoods.append(text)
                if "locality" in types_list:
                    localities.append(text)
                if "sublocality" in types_list:
                    sublocalities.append(text)
            if neighborhoods:
                extended["neighborhood"] = neighborhoods[0]
            if localities:
                extended["locality"] = localities[0]
            if sublocalities:
                extended["sublocality"] = sublocalities[0]

        sub_destinations = data.get("subDestinations", [])
        if sub_destinations:
            extended["sub_destinations"] = [
                {
                    "name": (
                        sd.get("name", {}).get("text")
                        if isinstance(sd.get("name"), dict)
                        else sd.get("name")
                    ),
                    "place_id": sd.get("id"),
                }
                for sd in sub_destinations
                if sd.get("name") or sd.get("id")
            ]

        return PlaceDetailResult(
            place_id=requested_place_id,
            display_name=(
                display_name_obj.get("text")
                if isinstance(display_name_obj, dict)
                else display_name_obj
            ),
            formatted_address=data.get("formattedAddress"),
            latitude=location.get("latitude"),
            longitude=location.get("longitude"),
            primary_type=data.get("primaryType"),
            types=data.get("types"),
            international_phone_number=data.get("internationalPhoneNumber"),
            national_phone_number=data.get("nationalPhoneNumber"),
            website_uri=data.get("websiteUri"),
            google_maps_uri=data.get("googleMapsUri"),
            rating=data.get("rating"),
            user_rating_count=data.get("userRatingCount"),
            business_status=data.get("businessStatus"),
            opening_hours=opening_hours,
            open_now=open_now,
            photos=photos,
            reviews=reviews,
            price_level=data.get("priceLevel"),
            wheelchair_accessible_entrance=accessibility.get(
                "wheelchairAccessibleEntrance"
            ),
            editorial_summary=(
                editorial_obj.get("text")
                if isinstance(editorial_obj, dict)
                else editorial_obj
            ),
            extended_data=extended if extended else None,
        )

    async def get_place_details(self, place_id: str) -> PlaceDetailResult:
        self._place_id_for_url = place_id
        logger.info("Google Place Details fetch — place_id: %s", place_id)

        try:
            data = await self._execute_request({}, context="Place Details")
            logger.info(
                "Google Place Details fetched successfully — place_id: %s", place_id
            )
            return self._parse_response(data, place_id)

        except httpx.TimeoutException:
            logger.error(
                "Google Place Details request timed out for place_id: %s", place_id
            )
            raise GooglePlacesTimeoutError()

        except GooglePlacesAPIError as exc:
            if getattr(exc, "provider_status_code", None) == 404:
                logger.warning("Google Place Details: place_id %s not found", place_id)
                raise PlaceDetailNotFoundError(place_id)
            raise
