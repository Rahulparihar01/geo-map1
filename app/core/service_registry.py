from sqlalchemy.orm import Session

from app.integrations.google_autocomplete import GoogleAutocompleteClient
from app.integrations.google_place_details import GooglePlaceDetailsClient
from app.integrations.google_places import GooglePlacesClient
from app.integrations.google_routes import GoogleRoutesClient
from app.integrations.google_text_search import GoogleTextSearchClient
from app.repositories.redis_repository import RedisRepository
from app.services.discovery_service import DiscoveryService
from app.services.knowledge_service import KnowledgeService
from app.services.place_details_service import PlaceDetailsService
from app.services.routes_service import RoutesService


class ServiceRegistry:
    def __init__(self, app_state):
        self.app_state = app_state

    def get_discovery_service(
        self, db: Session, redis_repo: RedisRepository
    ) -> DiscoveryService:
        http_text = getattr(self.app_state, "http_text_search", None)
        http_nearby = getattr(self.app_state, "http_nearby", None)
        http_autocomplete = getattr(self.app_state, "http_autocomplete", None)
        
        openai_client = getattr(self.app_state, "openai_client", None)

        return DiscoveryService(
            db=db,
            redis_repo=redis_repo,
            text_client=GoogleTextSearchClient(http_client=http_text),
            nearby_client=GooglePlacesClient(http_client=http_nearby),
            autocomplete_client=GoogleAutocompleteClient(http_client=http_autocomplete),
            openai_client=openai_client,
        )

    def get_place_details_service(
        self, db: Session, redis_repo: RedisRepository
    ) -> PlaceDetailsService:
        http_client = getattr(self.app_state, "http_place_details", None)
        openai_client = getattr(self.app_state, "openai_client", None)
        pinecone_client = getattr(self.app_state, "pinecone_client", None)
        
        knowledge_service = None
        if openai_client and pinecone_client:
            knowledge_service = KnowledgeService(
                db=db,
                openai_client=openai_client,
                pinecone_client=pinecone_client,
            )

        return PlaceDetailsService(
            db=db,
            redis_repo=redis_repo,
            google_client=GooglePlaceDetailsClient(http_client=http_client),
            knowledge_service=knowledge_service,
        )

    def get_routes_service(
        self, db: Session, redis_repo: RedisRepository
    ) -> RoutesService:
        http_client = getattr(self.app_state, "http_routes", None)
        
        return RoutesService(
            db=db,
            redis_repo=redis_repo,
            routes_client=GoogleRoutesClient(http_client=http_client),
        )

