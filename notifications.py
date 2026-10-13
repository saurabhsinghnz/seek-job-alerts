import logging

import requests


logger = logging.getLogger("seek_job_alert")


def format_telegram_message(job: dict) -> str:
    """Format job details for Telegram message."""
    return (
        f"🔔 *New Job Alert!*\n\n"
        f"📌 *{job['title']}*\n"
        f"🏢 Company: {job['company']}\n"
        f"💰 Salary: {job['salary']}\n"
        f"📍 Location: {job['location']}\n\n"
        f"🔗 [View Job]({job['link']})"
    )


def send_telegram_notification(
    job: dict,
    *,
    chat_id: str,
    telegram_api_url: str,
    request_post=None,
):
    """Send job notification via Telegram using HTTP API."""
    try:
        payload = {
            'chat_id': chat_id,
            'text': format_telegram_message(job),
            'parse_mode': 'Markdown',
        }

        post = request_post or requests.post
        response = post(telegram_api_url, json=payload, timeout=10)

        if response.status_code != 200:
            logger.error("✗ Telegram API error (%s): %s", response.status_code, response.text)
            return

        try:
            response_body = response.json()
        except Exception:
            response_body = None

        if isinstance(response_body, dict) and response_body.get('ok') is False:
            logger.error(
                "✗ Telegram API error (%s): %s",
                response.status_code,
                response_body.get('description', response.text),
            )
            return

        logger.info("✓ Telegram notification sent for job: %s", job['title'])
    except Exception as error:
        logger.error("✗ Error sending Telegram notification: %s", error)