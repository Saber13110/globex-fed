import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.chat_collection import ChatCollection
from app.models.chat_message import ChatMessage
from app.core.database import get_db
from app.models.chat_session import ChatSession
from app.models.shared_conversation_link import SharedConversationLink
from app.models.user import User
from app.routes.deps import get_current_user
from app.schemas.chat import (
    ChatAiRequest,
    ChatAiResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    ExportDownloadSpec,
    ChatCollectionCreateRequest,
    ChatCollectionRead,
    ChatSessionMessageRead,
    ChatSessionRead,
    ChatSessionUpdateRequest,
    ImportSharedConversationResponse,
    ShareConversationCreateRequest,
    ShareConversationRead,
    SharedConversationPreview,
    ShipmentSummary,
)
from app.schemas.client_agent import AgentQuestionnaire, AgentReasoning, AgentStep, AgentSuggestion
from app.services import chatbot_service, llm_service
from app.services.activity_log_service import client_ip, mask_sensitive_text, write_log
from app.core.config import get_settings
from app.services.prompt_guard_service import RiskLevel, assess_user_message, must_block_preferences
from app.services.security_ids_service import record_prompt_guard_event
from app.services.llm.prompts import prompt_injection_refusal
from app.services.quota_service import enforce_daily_quota

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/ai", response_model=ChatAiResponse)
def chat_ai(payload: ChatAiRequest) -> ChatAiResponse:
    """
    Endpoint IA stateless : réponse LLM, intention, numéro extrait, fournisseur (gemini/ollama).
    Utile pour tests et intégration sans créer de session.
    """
    try:
        result = llm_service.generate_response(
            payload.message,
            response_preferences=payload.response_preferences,
            preferred_name=payload.preferred_name,
            ui_language=payload.ui_language,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return ChatAiResponse(
        reply=result.reply,
        intent=result.intent,
        tracking_number=result.tracking_number,
        llm_provider=result.llm_provider,
        fedex_data_available=result.fedex_data_available,
    )


@router.post("/message", response_model=ChatMessageResponse)
def post_message(
    payload: ChatMessageRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatMessageResponse:
    enforce_daily_quota(db, user, kind="messages")
    settings = get_settings()
    msg_check = (payload.message or "").strip()
    message_risk = None
    if settings.prompt_guard_enabled and msg_check:
        message_risk = assess_user_message(msg_check)
        blocked = settings.prompt_guard_block_chat and must_block_preferences(message_risk)
        if message_risk.level != RiskLevel.ok:
            record_prompt_guard_event(
                db,
                user_id=user.id,
                ip_address=client_ip(request),
                score=message_risk.score,
                reasons=message_risk.reasons,
                level=message_risk.level.value,
                message_preview=mask_sensitive_text(msg_check, max_len=120),
                blocked=blocked,
            )
        if blocked:
            write_log(
                db,
                action="security.prompt_blocked",
                message="Message chat bloqué (politique de sécurité)",
                category="security",
                level="WARNING",
                user_id=user.id,
                ip_address=client_ip(request),
                metadata={"reasons": message_risk.reasons, "score": message_risk.score},
                commit=True,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=prompt_injection_refusal(
                    payload.ui_language or getattr(user, "preferred_language", None) or "fr"
                ),
            )
    if payload.session_id is not None:
        session = db.get(ChatSession, payload.session_id)
        if session is None or session.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session introuvable")
    else:
        session = ChatSession(user_id=user.id, title="Nouvelle conversation")
        db.add(session)
        db.flush()
        write_log(
            db,
            action="chat.session_create",
            message="Nouvelle conversation créée",
            category="chat",
            level="INFO",
            user_id=user.id,
            ip_address=client_ip(request),
            metadata={"session_id": session.id},
        )

    session.updated_at = func.now()
    ui_lang = payload.ui_language or getattr(user, "preferred_language", None) or "fr"
    active_prefs = (user.response_preferences or "").strip() or None
    preview = mask_sensitive_text(msg_check or "[image]", max_len=120)
    chat_log_level = "INFO"
    chat_log_category = "chat"
    chat_log_action = "chat.user_message"
    if message_risk is not None and message_risk.level != RiskLevel.ok:
        chat_log_level = "WARNING"
        chat_log_category = "security"
        chat_log_action = "security.chat_probe"
    write_log(
        db,
        action=chat_log_action,
        message=f"Prompt : {preview}",
        category=chat_log_category,
        level=chat_log_level,
        user_id=user.id,
        ip_address=client_ip(request),
        metadata={
            "session_id": session.id,
            "has_image": bool(payload.image_base64),
            "has_document": bool(
                payload.image_base64
                and payload.image_mime_type
                and str(payload.image_mime_type).startswith("application/")
            ),
            "risk_score": message_risk.score if message_risk else 0,
            "risk_reasons": message_risk.reasons if message_risk else [],
            "risk_level": message_risk.level.value if message_risk else "ok",
        },
    )
    result = chatbot_service.process_user_message(
        db,
        user,
        payload.message,
        session,
        response_preferences=active_prefs,
        preferred_name=payload.preferred_name,
        ui_language=ui_lang,
        image_base64=payload.image_base64,
        image_mime_type=payload.image_mime_type,
        file_name=payload.file_name,
        agent_mode=payload.agent_mode,
        agent_flow_id=payload.agent_flow_id,
        agent_answers=payload.agent_answers,
    )
    write_log(
        db,
        action="chat.bot_reply",
        message=f"Réponse ({result.get('source', 'unknown')}) — session « {result.get('session_title', session.title)} »",
        category="chat",
        level="INFO",
        user_id=user.id,
        ip_address=client_ip(request),
        metadata={
            "session_id": session.id,
            "intent": result.get("intent"),
            "tracking_number": result.get("tracking_number"),
            "source": result.get("source"),
        },
    )
    shipment = result.get("shipment")
    export_dl = result.get("export_download")
    agent_q = result.get("agent_questionnaire")
    agent_steps = result.get("agent_steps") or []
    agent_sug = result.get("agent_suggestion")
    agent_reasoning = result.get("agent_reasoning")

    return ChatMessageResponse(
        reply=result["reply"],
        session_id=result["session_id"],
        session_title=result.get("session_title"),
        source=result.get("source", "unknown"),
        shipment=ShipmentSummary(**shipment) if shipment else None,
        intent=result.get("intent"),
        tracking_number=result.get("tracking_number"),
        llm_provider=result.get("llm_provider"),
        export_download=ExportDownloadSpec(**export_dl) if export_dl else None,
        agent_mode=bool(result.get("agent_mode")),
        agent_phase=result.get("agent_phase"),
        agent_questionnaire=AgentQuestionnaire(**agent_q) if agent_q else None,
        agent_steps=[AgentStep(**s) for s in agent_steps if isinstance(s, dict)],
        agent_reasoning=AgentReasoning(**agent_reasoning) if agent_reasoning else None,
        agent_suggestion=AgentSuggestion(**agent_sug) if agent_sug else None,
        tools_used=result.get("tools_used") or [],
        gpt_slug=result.get("gpt_slug"),
        knowledge_hits=int(result.get("knowledge_hits") or 0),
    )


@router.post("/agent/watches/check")
def check_my_shipment_watches(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """Force la vérification Visibility + notifications pour les colis surveillés du client."""
    from app.models.shipment_watch import ShipmentWatch
    from app.services.shipment_watch_service import process_single_watch

    watches = list(
        db.scalars(
            select(ShipmentWatch).where(
                ShipmentWatch.user_id == user.id,
                ShipmentWatch.is_active.is_(True),
            )
        ).all()
    )
    checked = 0
    for watch in watches:
        if process_single_watch(db, watch):
            checked += 1
    db.commit()
    return {"active_watches": len(watches), "checked": checked}


@router.get("/sessions", response_model=list[ChatSessionRead])
def list_sessions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=300),
    search: str | None = Query(default=None, max_length=120),
    collection_id: int | None = Query(default=None, ge=1),
    smart_view: str = Query(default="all"),
    include_archived: bool = Query(default=False),
) -> list[ChatSession]:
    stmt = select(ChatSession).where(ChatSession.user_id == user.id)

    if not include_archived:
        stmt = stmt.where(ChatSession.is_archived.is_(False))
    if search:
        s = f"%{search.strip()}%"
        stmt = stmt.where(ChatSession.title.ilike(s))
    if collection_id is not None:
        stmt = stmt.where(ChatSession.collection_id == collection_id)

    view = smart_view.strip().lower()
    if view == "pinned":
        stmt = stmt.where(ChatSession.is_pinned.is_(True))
    elif view == "recent":
        stmt = stmt.where(ChatSession.updated_at >= func.now() - func.make_interval(days=7))
    elif view == "exports":
        stmt = stmt.where(ChatSession.title.ilike("%export%"))
    elif view == "active":
        stmt = stmt.where(ChatSession.is_archived.is_(False))

    stmt = stmt.order_by(ChatSession.is_pinned.desc(), ChatSession.updated_at.desc(), ChatSession.created_at.desc()).limit(
        limit
    )
    return list(db.scalars(stmt).all())


@router.get("/sessions/{session_id}/messages", response_model=list[ChatSessionMessageRead])
def get_session_messages(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ChatMessage]:
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session introuvable")
    stmt = select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at.asc())
    return list(db.scalars(stmt).all())


@router.patch("/sessions/{session_id}", response_model=ChatSessionRead)
def update_session(
    session_id: int,
    payload: ChatSessionUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session introuvable")

    if payload.title is not None:
        cleaned = payload.title.strip()
        if not cleaned:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Titre invalide")
        session.title = cleaned[:255]

    if payload.collection_id is not None:
        if payload.collection_id <= 0:
            session.collection_id = None
        else:
            collection = db.get(ChatCollection, payload.collection_id)
            if collection is None or collection.user_id != user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")
            session.collection_id = payload.collection_id

    if payload.tags is not None:
        session.tags = payload.tags.strip()[:800]

    if payload.is_pinned is not None:
        session.is_pinned = payload.is_pinned
    if payload.is_archived is not None:
        session.is_archived = payload.is_archived

    session.updated_at = func.now()
    write_log(
        db,
        action="chat.session_update",
        message=f"Conversation modifiée : « {session.title[:80]} »",
        category="chat",
        level="INFO",
        user_id=user.id,
        ip_address=client_ip(request),
        metadata={"session_id": session.id},
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session introuvable")
    title = session.title
    write_log(
        db,
        action="chat.session_delete",
        message=f"Conversation supprimée : « {title[:80]} »",
        category="chat",
        level="WARNING",
        user_id=user.id,
        ip_address=client_ip(request),
        metadata={"session_id": session_id},
    )
    db.delete(session)
    db.commit()


@router.get("/collections", response_model=list[ChatCollectionRead])
def list_collections(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ChatCollection]:
    stmt = select(ChatCollection).where(ChatCollection.user_id == user.id).order_by(ChatCollection.created_at.desc())
    return list(db.scalars(stmt).all())


@router.post("/collections", response_model=ChatCollectionRead, status_code=status.HTTP_201_CREATED)
def create_collection(
    payload: ChatCollectionCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatCollection:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nom de dossier invalide")
    row = ChatCollection(user_id=user.id, name=name[:120])
    db.add(row)
    db.flush()
    write_log(
        db,
        action="chat.collection_create",
        message=f"Dossier créé : « {name[:80]} »",
        category="chat",
        level="INFO",
        user_id=user.id,
        ip_address=client_ip(request),
        metadata={"collection_id": row.id},
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/sessions/{session_id}/share", response_model=ShareConversationRead)
def create_or_update_share_link(
    session_id: int,
    payload: ShareConversationCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShareConversationRead:
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session introuvable")

    stmt = select(SharedConversationLink).where(
        SharedConversationLink.session_id == session.id,
        SharedConversationLink.owner_user_id == user.id,
        SharedConversationLink.is_active.is_(True),
    )
    share_row = db.scalar(stmt)
    if share_row is None:
        share_row = SharedConversationLink(
            session_id=session.id,
            owner_user_id=user.id,
            share_token=secrets.token_urlsafe(24),
            include_tracking_details=payload.include_tracking_details,
            is_active=True,
        )
    else:
        share_row.include_tracking_details = payload.include_tracking_details

    db.add(share_row)
    db.flush()
    token_hint = share_row.share_token[-6:] if share_row.share_token else ""
    write_log(
        db,
        action="chat.share_create",
        message=f"Lien de partage créé (…{token_hint})",
        category="chat",
        level="INFO",
        user_id=user.id,
        ip_address=client_ip(request),
        metadata={
            "session_id": session.id,
            "include_tracking": payload.include_tracking_details,
        },
    )
    db.commit()
    db.refresh(share_row)
    return ShareConversationRead(
        share_token=share_row.share_token,
        include_tracking_details=share_row.include_tracking_details,
    )


@router.get("/shared/{share_token}", response_model=SharedConversationPreview)
def get_shared_conversation(
    share_token: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SharedConversationPreview:
    share_row = db.scalar(
        select(SharedConversationLink).where(
            SharedConversationLink.share_token == share_token,
            SharedConversationLink.is_active.is_(True),
        )
    )
    if share_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lien de partage introuvable")

    session = db.get(ChatSession, share_row.session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session introuvable")

    messages = list(
        db.scalars(select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at.asc())).all()
    )
    if not share_row.include_tracking_details:
        messages = [
            ChatMessage(
                id=m.id,
                session_id=m.session_id,
                sender=m.sender,
                source=m.source,
                message_text=m.message_text,
                created_at=m.created_at,
            )
            for m in messages
            if m.sender == "user" or (m.sender == "bot" and "tracking_number" not in m.message_text.lower())
        ]

    return SharedConversationPreview(
        session_id=session.id,
        title=session.title,
        include_tracking_details=share_row.include_tracking_details,
        messages=[ChatSessionMessageRead.model_validate(m) for m in messages],
    )


@router.post("/shared/{share_token}/import", response_model=ImportSharedConversationResponse)
def import_shared_conversation(
    share_token: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ImportSharedConversationResponse:
    share_row = db.scalar(
        select(SharedConversationLink).where(
            SharedConversationLink.share_token == share_token,
            SharedConversationLink.is_active.is_(True),
        )
    )
    if share_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lien de partage introuvable")

    source_session = db.get(ChatSession, share_row.session_id)
    if source_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session introuvable")

    new_session = ChatSession(
        user_id=user.id,
        title=f"{source_session.title} (partagé)",
        collection_id=None,
        tags=source_session.tags,
        is_pinned=False,
        is_archived=False,
    )
    db.add(new_session)
    db.flush()

    source_messages = list(
        db.scalars(select(ChatMessage).where(ChatMessage.session_id == source_session.id).order_by(ChatMessage.created_at.asc())).all()
    )
    for m in source_messages:
        db.add(
            ChatMessage(
                session_id=new_session.id,
                sender=m.sender,
                source=m.source,
                message_text=m.message_text,
            )
        )

    write_log(
        db,
        action="chat.share_import",
        message=f"Conversation importée depuis un lien (…{share_token[-6:]})",
        category="chat",
        level="INFO",
        user_id=user.id,
        ip_address=client_ip(request),
        metadata={"new_session_id": new_session.id, "source_session_id": source_session.id},
        commit=False,
    )
    db.commit()
    return ImportSharedConversationResponse(session_id=new_session.id)
