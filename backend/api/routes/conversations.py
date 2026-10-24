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
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationItem,
    ConversationListResponse,
    ConversationMessageCreateRequest,
    ConversationMessageItem,
)
from backend.auth.permissions import Permission
from backend.database.unit_of_work import UnitOfWork

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


def _conversation_item(conversation) -> ConversationItem:
    messages = getattr(conversation, "messages", None) or []
    return ConversationItem(
        conversation_id=conversation.id,
        customer_id=conversation.customer_id,
        user_id=conversation.user_id,
        channel=conversation.channel,
        subject=conversation.subject,
        status=conversation.status,
        started_at=conversation.started_at,
        resolved_at=conversation.resolved_at,
        message_count=len(messages),
    )


def _message_item(message) -> ConversationMessageItem:
    return ConversationMessageItem(
        message_id=message.id,
        author_id=message.author_id,
        author_type=message.author_type,
        role=message.role,
        body=message.body,
        visibility=message.visibility,
        created_at=message.created_at,
    )


def _detail_response(request_id: str, conversation) -> ConversationDetailResponse:
    messages = getattr(conversation, "messages", None) or []
    return ConversationDetailResponse(
        request_id=request_id,
        conversation=_conversation_item(conversation),
        messages=[_message_item(message) for message in sorted(messages, key=lambda item: item.created_at)],
    )


@router.post("", response_model=ConversationDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreateRequest,
    context: RequestContext = Depends(require_permission(Permission.CONVERSATION_CREATE)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> ConversationDetailResponse:
    if payload.customer_id is None and payload.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_conversation_target", "message": "customer_id or user_id is required"},
        )
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        conversation = await uow.support.create_conversation(
            scope=context.scope,
            customer_id=payload.customer_id,
            user_id=payload.user_id,
            channel=payload.channel,
            subject=payload.subject,
        )
        if payload.initial_message:
            await uow.support.append_conversation_message(
                scope=context.scope,
                conversation_id=conversation.id,
                author_id=context.scope.actor_id,
                author_type="user",
                role="user",
                body=payload.initial_message,
                visibility="public",
            )
        conversation = await uow.support.get_conversation(
            scope=context.scope,
            conversation_id=conversation.id,
        )
        assert conversation is not None
    return _detail_response(request_id=context.request_id, conversation=conversation)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    context: RequestContext = Depends(require_permission(Permission.CONVERSATION_READ)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> ConversationListResponse:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        conversations = await uow.support.list_conversations(
            scope=context.scope,
            limit=50,
        )
    return ConversationListResponse(
        request_id=context.request_id,
        conversations=[_conversation_item(item) for item in conversations],
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: UUID,
    context: RequestContext = Depends(require_permission(Permission.CONVERSATION_READ)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> ConversationDetailResponse:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        conversation = await uow.support.get_conversation(
            scope=context.scope,
            conversation_id=conversation_id,
        )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "conversation_not_found", "message": "conversation not found"},
        )
    return _detail_response(request_id=context.request_id, conversation=conversation)


@router.post("/{conversation_id}/messages", response_model=ConversationDetailResponse, status_code=status.HTTP_201_CREATED)
async def append_conversation_message(
    conversation_id: UUID,
    payload: ConversationMessageCreateRequest,
    context: RequestContext = Depends(require_permission(Permission.CONVERSATION_WRITE)),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> ConversationDetailResponse:
    async with UnitOfWork(session_factory, scope=context.scope) as uow:
        await uow.support.append_conversation_message(
            scope=context.scope,
            conversation_id=conversation_id,
            author_id=context.scope.actor_id,
            author_type="user",
            role=payload.role,
            body=payload.body,
            visibility=payload.visibility,
        )
        conversation = await uow.support.get_conversation(
            scope=context.scope,
            conversation_id=conversation_id,
        )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "conversation_not_found", "message": "conversation not found"},
        )
    return _detail_response(request_id=context.request_id, conversation=conversation)


__all__ = ["router"]
