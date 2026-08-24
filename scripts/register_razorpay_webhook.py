#!/usr/bin/env python3

import sys
import asyncio
import logging

# Add parent directory to path
sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])

from app.services.razorpay_service import RazorpayService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    if len(sys.argv) < 2:
        print("Usage: python register_razorpay_webhook.py <webhook_url>")
        print("Example: python register_razorpay_webhook.py https://tinderbox-hazelnut-guileless.ngrok-free.dev")
        sys.exit(1)

    webhook_url = sys.argv[1]
    if not webhook_url.endswith("/"):
        webhook_url += "/"
    webhook_url += "payments/webhook"

    logger.info(f"Registering webhook with URL: {webhook_url}")

    try:
        webhook = await RazorpayService.create_webhook(url=webhook_url)
        
        print("\n" + "=" * 80)
        print("✅ WEBHOOK REGISTERED SUCCESSFULLY!")
        print("=" * 80)
        print(f"\nWebhook ID:       {webhook['id']}")
        print(f"URL:              {webhook['url']}")
        print(f"Events:           {', '.join(webhook['events'])}")
        print(f"\n🔐 SIGNING SECRET (save this!):")
        print(f"{webhook['signing_secret']}")
        print("\nAdd this to your .env file:")
        print(f"RAZORPAY_WEBHOOK_SECRET={webhook['signing_secret']}")
        print("\n" + "=" * 80)
        
    except Exception as exc:
        logger.error(f"Failed to register webhook: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
