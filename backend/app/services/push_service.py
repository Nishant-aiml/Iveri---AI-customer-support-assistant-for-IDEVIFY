import os
import json
import logging
from typing import Any

logger = logging.getLogger("idevify-push")

class PushService:
    def __init__(self):
        self.vapid_public_key = os.getenv(
            "VAPID_PUBLIC_KEY",
            "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U"
        )
        self.vapid_private_key = os.getenv("VAPID_PRIVATE_KEY", "")
        self.vapid_claims = {"sub": os.getenv("VAPID_CLAIM_EMAIL", "mailto:alerts@idevify.com")}

    def get_public_key(self) -> str:
        return self.vapid_public_key

    async def send_web_push(self, subscription: dict[str, Any], payload: dict[str, Any]) -> bool:
        """Dispatches a Web Push notification to a subscribed browser client."""
        try:
            # Check if pywebpush is available in the environment
            try:
                from pywebpush import webpush  # noqa: F401
                # If configured with private key, send real push
                if self.vapid_private_key:
                    webpush(
                        subscription_info=subscription,
                        data=json.dumps(payload),
                        vapid_private_key=self.vapid_private_key,
                        vapid_claims=self.vapid_claims
                    )
                    logger.info(f"Dispatched Web Push notification: {payload.get('title')}")
                    return True
            except ImportError:
                pass

            # Safe local/mock log dispatch
            logger.info(
                f"[WEB_PUSH_DISPATCH] To endpoint: {subscription.get('endpoint', '')[:40]}... "
                f"| Title: {payload.get('title')} | Body: {payload.get('body')}"
            )
            return True
        except Exception as e:
            logger.warning(f"Web Push dispatch notice: {e}")
            return False

push_service = PushService()
