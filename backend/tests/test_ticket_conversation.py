import sys
import os
from datetime import datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.schemas.ticket import TicketConversationResponse, UnansweredConversationMessage

def test_ticket_conversation_schema():
    msg = UnansweredConversationMessage(
        id="msg-1",
        sender="customer",
        content="What is your return policy?",
        is_answered=False,
        is_unanswered_target=True,
        created_at=datetime.utcnow(),
        sentiment="neutral"
    )
    assert msg.is_unanswered_target is True
    assert msg.sender == "customer"

    conv = TicketConversationResponse(
        ticket_id="tick-1",
        ticket_number="TICK-1001",
        session_id="sess-1",
        channel="widget",
        status="open",
        priority="medium",
        unanswered_question="What is your return policy?",
        messages=[msg],
        has_chat_session=True
    )
    assert conv.ticket_number == "TICK-1001"
    assert len(conv.messages) == 1
    assert conv.messages[0].is_unanswered_target is True
