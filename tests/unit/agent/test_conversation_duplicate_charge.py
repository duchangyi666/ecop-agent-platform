from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from backend.agent.actions import ConversationActionExecutor


def test_duplicate_candidates_must_share_invoice():
    now = datetime.now(timezone.utc)
    invoice_id = uuid4()
    first = SimpleNamespace(invoice_id=invoice_id, amount=Decimal("100.00"), paid_at=now)
    other_invoice = SimpleNamespace(invoice_id=uuid4(), amount=first.amount, paid_at=now + timedelta(minutes=1))
    same_invoice = SimpleNamespace(invoice_id=invoice_id, amount=first.amount, paid_at=now + timedelta(minutes=2))

    assert ConversationActionExecutor._find_duplicate([first, other_invoice]) is None
    assert ConversationActionExecutor._find_duplicate([first, other_invoice, same_invoice]) is same_invoice
