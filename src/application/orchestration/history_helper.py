import json
import uuid
from sqlalchemy.orm import Session
from src.infrastructure.db.models import ConversationORM, MessageORM
from src.ports.llm_gateway import LLMMessage


def fetch_conversation_history(
    db: Session,
    project_id: uuid.UUID,
    max_turns: int = 8,
    max_content_chars: int = 1500,
) -> list[LLMMessage]:
    conv = db.query(ConversationORM).filter_by(project_id=project_id).first()
    if not conv:
        return []

    raw_messages = (
        db.query(MessageORM)
        .filter(MessageORM.conversation_id == conv.id)
        .order_by(MessageORM.created_date.desc())
        .limit(max_turns * 2)
        .all()
    )

    history: list[LLMMessage] = []

    for msg in reversed(raw_messages):
        content = (msg.content or "").strip()
        if not content:
            continue

        if msg.metadata_json:
            try:
                meta = json.loads(msg.metadata_json)
                if meta.get("isApprovalCard") or meta.get("approvalRequired"):
                    continue
            except Exception:
                pass

        if content.startswith("Analyzing requested changes for") or content.startswith("⚠️ Workflow Execution Error:"):
            continue

        role = "user" if msg.sender_type.lower() == "user" else "assistant"

        if len(content) > max_content_chars and role == "assistant":
            content = content[:max_content_chars].rstrip() + "\n...[truncated for brevity]..."

        history.append(LLMMessage(role=role, content=content))

    return history[-max_turns:]
