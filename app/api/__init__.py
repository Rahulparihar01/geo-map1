from fastapi import APIRouter
from app.api import (
    ai_chat,
    auth,
    comparison,
    discovery,
    knowledge,
    locations,
    place_details,
    place_qa,
    place_unlock,
    razorpay_payments,
    razorpay_webhook,
    routes,
    saved_places as saved_places_router,
    visits as visits_router,
    weather, ws,)

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(ws.router)
api_router.include_router(locations.router)
api_router.include_router(discovery.router)
api_router.include_router(place_unlock.router)
api_router.include_router(place_details.router)
api_router.include_router(knowledge.router)
api_router.include_router(place_qa.router)
api_router.include_router(ai_chat.router)
api_router.include_router(routes.router)
api_router.include_router(weather.router)
api_router.include_router(saved_places_router.router)
api_router.include_router(visits_router.router)
api_router.include_router(comparison.router)
api_router.include_router(razorpay_payments.router)
api_router.include_router(razorpay_webhook.router)
