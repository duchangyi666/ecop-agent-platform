from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.dependencies import (
    RequestContext,
    get_session_factory_dependency,
    require_permission,
)
from backend.api.schemas import (
    RuntimeAgentItem,
    RuntimeAgentListResponse,
    RuntimeCostResponse,
    RuntimeSpanItem,
    RuntimeTraceDetailResponse,
    RuntimeTraceItem,
    RuntimeTraceListResponse,
)
from backend.auth.permissions import Permission
from backend.database.unit_of_work import UnitOfWork

router = APIRouter(prefix="/api/v1/runtime", tags=["runtime"])


def _trace_item(trace) -> RuntimeTraceItem:
    return RuntimeTraceItem(
        trace_id=trace.id,
        trace_key=trace.trace_key,
        status=trace.status,
        entrypoint=trace.entrypoint,
        started_at=trace.started_at,
        finished_at=trace.finished_at,
        total_cost=trace.total_cost,
        error_summary=trace.error_summary,
    )


@router.get("/traces", response_model=RuntimeTraceListResponse)
async def list_runtime_traces(
    context: RequestContext = Depends(require_permission(Permission.RUNTIME_READ)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> RuntimeTraceListResponse:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        traces = await uow.runtime.list_traces(
            scope=context.scope,
            limit=50,
        )
    return RuntimeTraceListResponse(
        request_id=context.request_id,
        traces=[_trace_item(trace) for trace in traces],
    )


@router.get("/traces/{trace_id}", response_model=RuntimeTraceDetailResponse)
async def get_runtime_trace_detail(
    trace_id: UUID,
    context: RequestContext = Depends(require_permission(Permission.RUNTIME_READ)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> RuntimeTraceDetailResponse:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        trace = await uow.runtime.get_trace(
            scope=context.scope,
            trace_id=trace_id,
        )
        if trace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "trace_not_found", "message": "runtime trace not found"},
            )
        spans = await uow.runtime.list_spans(
            scope=context.scope,
            trace_id=trace.id,
        )
    return RuntimeTraceDetailResponse(
        request_id=context.request_id,
        trace=_trace_item(trace),
        spans=[
            RuntimeSpanItem(
                span_id=span.id,
                node_name=span.node_name,
                status=span.status,
                input_summary=span.input_summary,
                output_summary=span.output_summary,
                started_at=span.started_at,
                duration_ms=span.duration_ms,
            )
            for span in spans
        ],
    )


@router.get("/costs", response_model=RuntimeCostResponse)
async def get_runtime_costs(
    context: RequestContext = Depends(require_permission(Permission.RUNTIME_READ)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> RuntimeCostResponse:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        summary = await uow.runtime.summary(scope=context.scope)
    return RuntimeCostResponse(
        request_id=context.request_id,
        trace_count=summary["trace_count"],
        total_input_tokens=summary["total_input_tokens"],
        total_output_tokens=summary["total_output_tokens"],
        total_cost=summary["total_cost"],
        failed_count=summary["failed_count"],
    )


@router.get("/agents", response_model=RuntimeAgentListResponse)
async def list_runtime_agents(
    context: RequestContext = Depends(require_permission(Permission.RUNTIME_READ)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> RuntimeAgentListResponse:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        agents = await uow.runtime.list_agents(scope=context.scope)
    return RuntimeAgentListResponse(
        request_id=context.request_id,
        agents=[
            RuntimeAgentItem(
                agent_id=agent.id,
                agent_code=agent.agent_code,
                name=agent.name,
                status=agent.status,
            )
            for agent in agents
        ],
    )


__all__ = ["router"]
