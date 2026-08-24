import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.integrations.google_base import GoogleAPIClientBase

logger = logging.getLogger(__name__)

_FIELD_MASK = ",".join(
    [
        "suggestions.placePrediction.placeId",
        "suggestions.placePrediction.text",
        "suggestions.placePrediction.structuredFormat",
        "suggestions.placePrediction.types",
    ]
)


class GoogleAutocompleteClient(GoogleAPIClientBase):

    def _get_url(self) -> str:
        return f"{settings.GOOGLE_PLACES_BASE_URL}/places:autocomplete"

    def _get_field_mask(self) -> str:
        return _FIELD_MASK

    def _build_request_body(
        self,
        input_text: str,
        location_bias_lat: Optional[float],
        location_bias_lon: Optional[float],
        location_bias_radius: Optional[float],
        included_primary_types: Optional[List[str]],
        language_code: Optional[str],
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "input": input_text,
        }

        if (
            location_bias_lat is not None
            and location_bias_lon is not None
            and location_bias_radius is not None
        ):
            body["locationBias"] = {
                "circle": {
                    "center": {
                        "latitude": location_bias_lat,
                        "longitude": location_bias_lon,
                    },
                    "radius": location_bias_radius,
                }
            }

        if included_primary_types:
            body["includedPrimaryTypes"] = included_primary_types

        body["languageCode"] = language_code or "en"

        return body

    def _parse_predictions(self, raw_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        suggestions = raw_response.get("suggestions", [])
        predictions = []

        for suggestion in suggestions:
            place_prediction = suggestion.get("placePrediction")
            if not place_prediction:
                continue

            structured = place_prediction.get("structuredFormat", {})
            main_text = structured.get("mainText", {}).get("text", "")
            secondary_text = structured.get("secondaryText", {}).get("text", "")

            predictions.append(
                {
                    "place_id": place_prediction.get("placeId", ""),
                    "main_text": main_text,
                    "secondary_text": secondary_text,
                    "full_text": place_prediction.get("text", {}).get("text", ""),
                    "types": place_prediction.get("types", []),
                }
            )

        return predictions

    async def autocomplete(
        self,
        input_text: str,
        location_bias_lat: Optional[float] = None,
        location_bias_lon: Optional[float] = None,
        location_bias_radius: Optional[float] = 5000.0,
        included_primary_types: Optional[List[str]] = None,
        language_code: str = "en",
    ) -> List[Dict[str, Any]]:
        body = self._build_request_body(
            input_text=input_text,
            location_bias_lat=location_bias_lat,
            location_bias_lon=location_bias_lon,
            location_bias_radius=location_bias_radius,
            included_primary_types=included_primary_types,
            language_code=language_code,
        )

        data = await self._execute_request(body, context="Autocomplete")
        predictions = self._parse_predictions(data)

        logger.info(
            "Autocomplete complete — input: %r, predictions: %d",
            input_text,
            len(predictions),
        )
        return predictions
