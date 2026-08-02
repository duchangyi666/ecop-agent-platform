from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agent.consultation_workflow import (
    CustomerConsultationService,
    CustomerConsultationWorkflowRequest,
)
from backend.agent.state import create_agent_state
from backend.api.dependencies import (
    RequestContext,
    get_app_model_gateway,
    get_knowledge_vector_store,
    get_session_factory_dependency,
    require_permission,
)
from backend.api.schemas import CustomerConsultationRequest, CustomerConsultationResponse
from backend.llm.gateway import ModelGateway
from backend.rag.retriever import ConsultationKnowledgeRetriever
from backend.rag.vector_store import KnowledgeVectorStore

router = APIRouter(prefix="/api/v1", tags=["customer-service"])


@router.post("/customer-consultations", response_model=CustomerConsultationResponse)
async def create_customer_consultation(
    payload: CustomerConsultationRequest,
    response: Response,
    context: RequestContext = Depends(require_permission("customer.consult")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
    model_gateway: ModelGateway = Depends(get_app_model_gateway),
    vector_store: KnowledgeVectorStore | None = Depends(get_knowledge_vector_store),
) -> CustomerConsultationResponse:
    request = CustomerConsultationWorkflowRequest(
        thread_id=payload.thread_id,
        state=create_agent_state(
            scope=context.scope,
            request_id=uuid4(),
            message=payload.message,
        ),
    )
    result = await CustomerConsultationService(
        session_factory,
        model_gateway=model_gateway,
        knowledge_retriever=ConsultationKnowledgeRetriever(
            session_factory,
            vector_store=vector_store,
        ),
    ).run(request)

    if result.status == "blocked":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "security_blocked",
                "message": result.final_response or "request blocked",
            },
        )
    if result.status == "out_of_scope":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "out_of_scope",
                "message": result.final_response or "request out of scope",
            },
        )
    if result.status == "human_handoff":
        response.status_code = status.HTTP_202_ACCEPTED

    return CustomerConsultationResponse.from_result(
        request_id=context.request_id,
        result=result,
    )


__all__ = ["router"]
