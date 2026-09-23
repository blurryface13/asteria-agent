"""Canonical AgentOrchestrator API; legacy routes share the same persisted turns."""
from fastapi import APIRouter
from .coordinator import capabilities, read, route, shutdown

router = APIRouter(prefix='/api/orchestrator', tags=['orchestrator'])
router.add_api_route('/capabilities', capabilities, methods=['GET'])
router.add_api_route('/route', route, methods=['POST'])
router.add_api_route('/turn', read, methods=['GET'])
