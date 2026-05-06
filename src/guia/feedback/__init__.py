"""Módulo de feedback explícito (👍/👎) — dataset para training."""
from __future__ import annotations

from guia.feedback.models import ChatFeedback
from guia.feedback.repository import ChatFeedbackRepository

__all__ = ["ChatFeedback", "ChatFeedbackRepository"]
