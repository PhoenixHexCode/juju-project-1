"""Reference skill agents that demonstrate the orchestrator pattern.

These are *not* called automatically — the orchestrator's planning step decides
when to invoke them by including them in its `tools` list. They're shipped as
worked examples of two of the request scenarios:

  - booking_call: phone an external service (restaurant) with disclosure
  - app_builder: drive a remote dev box to scaffold and test a new app
"""
from .booking_call import BookingCallSkill
from .app_builder import AppBuilderSkill

__all__ = ["BookingCallSkill", "AppBuilderSkill"]
