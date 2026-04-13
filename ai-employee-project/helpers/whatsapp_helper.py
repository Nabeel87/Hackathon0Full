#!/usr/bin/env python3
"""
helpers/whatsapp_helper.py
Utility functions for WhatsApp message processing.
"""

import re
from datetime import datetime

# UI artifacts that appear in WhatsApp Web list view
_UI_ARTIFACTS = [
    "Typing...", "Online", "last seen",
    "voice call", "video call",
    "Photo", "Video", "Document",
    "Sticker", "GIF", "Audio",
    "You:", "Missed voice call", "Missed video call",
]


def clean_whatsapp_message(raw_text: str) -> str:
    """Remove WhatsApp UI artifacts and timestamps from message text."""
    cleaned = raw_text

    for artifact in _UI_ARTIFACTS:
        cleaned = cleaned.replace(artifact, "")

    # Remove timestamps: "10:36 AM", "10:36", "2:30 PM"
    cleaned = re.sub(r'\b\d{1,2}:\d{2}(?:\s*[AaPp][Mm])?\b', '', cleaned)

    # Collapse extra whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned)

    return cleaned.strip()


def extract_phone_number(text: str) -> str | None:
    """Extract phone number from text if present."""
    patterns = [
        r'\+\d{1,3}\s?\d{3}\s?\d{7,8}',   # +92 300 1234567
        r'\+\d{1,3}\d{10}',                 # +923001234567
        r'\b0\d{10}\b',                      # 03001234567
        r'\(\d{3}\)\s?\d{7}',               # (300) 1234567
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def is_business_message(text: str, business_keywords: list[str]) -> bool:
    """Return True if text contains at least one business keyword."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in business_keywords)


def detect_priority(text: str, high_priority_keywords: list[str]) -> str:
    """Return 'high' if text contains a high-priority keyword, else 'normal'."""
    text_lower = text.lower()
    for kw in high_priority_keywords:
        if kw in text_lower:
            return "high"
    return "normal"


def create_message_fingerprint(sender: str, message: str) -> str:
    """
    Create a content-based fingerprint for deduplication.
    Uses sender name + first 50 characters of message text.
    """
    sender_clean  = sender.strip().lower()
    message_clean = message.strip()[:50].lower()
    return f"{sender_clean}|{message_clean}"


def format_whatsapp_task(
    sender: str,
    message: str,
    phone: str | None = None,
    priority: str = "normal",
) -> str:
    """Format WhatsApp message data as a vault task file content string."""
    timestamp = datetime.now().isoformat()
    phone_str = phone or "Unknown"

    return f"""---
type: whatsapp_message
from: {sender}
phone: {phone_str}
received: {timestamp}
priority: {priority}
status: pending
---

# WhatsApp Message

**From:** {sender}
**Phone:** {phone_str}
**Received:** {timestamp}
**Priority:** {priority}

---

## Message Preview

{message}

## Suggested Actions
- [ ] Reply on WhatsApp
- [ ] Mark as important
- [ ] Create follow-up task
- [ ] Schedule reminder

---
*WhatsApp message detected by AI Employee*
"""
