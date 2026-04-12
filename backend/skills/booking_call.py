"""Booking call skill — restaurant reservation example.

Flow when invoked by an orchestrator agent:
  1. Calendar sub-agent checks the user's free slots in the next N days.
  2. Restaurant search sub-agent finds candidates within driving radius.
  3. This skill places an outbound Twilio call to the chosen restaurant
     using a TTS-driven IVR script. THE FIRST THING THE CALLER SAYS IS A
     DISCLOSURE: "Hi, this is an automated assistant calling on behalf of
     {user_name}. I'd like to make a reservation."  This is required by
     several US state and federal rules and is the right thing to do.
  4. On success, emails the user a confirmation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from ..config import get_settings

log = logging.getLogger(__name__)


@dataclass
class BookingRequest:
    user_name: str
    user_email: str
    restaurant_name: str
    restaurant_phone: str
    party_size: int
    iso_datetime: str
    notes: Optional[str] = None


class BookingCallSkill:
    def __init__(self):
        s = get_settings()
        self.sid = s.twilio_account_sid
        self.token = s.twilio_auth_token
        self.from_number = s.twilio_from_number
        self._client = None
        if self.sid and self.token:
            try:
                from twilio.rest import Client
                self._client = Client(self.sid, self.token)
            except ImportError:
                self._client = None

    @property
    def configured(self) -> bool:
        return self._client is not None and bool(self.from_number)

    def _twiml(self, req: BookingRequest) -> str:
        # Disclosure-first script. NEVER remove the disclosure line.
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Matthew">
    Hello, this is an automated assistant calling on behalf of {req.user_name}.
    I would like to make a reservation for {req.party_size} people
    at {req.restaurant_name} on {req.iso_datetime}.
    {req.notes or ''}
    A human will follow up by email to confirm. Thank you very much.
  </Say>
  <Pause length="1"/>
  <Hangup/>
</Response>"""

    def place_call(self, req: BookingRequest) -> dict:
        if not self.configured:
            return {
                "ok": False,
                "error": "Twilio not configured (set TWILIO_* in .env)",
            }
        call = self._client.calls.create(
            to=req.restaurant_phone,
            from_=self.from_number,
            twiml=self._twiml(req),
        )
        log.info("Placed booking call sid=%s", call.sid)
        return {"ok": True, "call_sid": call.sid}
