"""
Sends the 6-digit login verification code by email.

Uses the same QQ mailbox SMTP account already configured for the JChatMind
project (spring.mail in application.yaml) - same account, different client
(aiosmtplib instead of Spring's JavaMailSender).
"""
import os
import random
import logging
from email.mime.text import MIMEText
from email.header import Header

import aiosmtplib

logger = logging.getLogger(__name__)


def generate_code() -> str:
    return f"{random.randint(0, 999999):06d}"


async def send_verification_code(to_email: str, code: str, expire_minutes: int):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ["SMTP_PORT"])
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]

    subject = "Bunny Research 登录验证码"
    body = (
        f"你的登录验证码是: {code}\n\n"
        f"{expire_minutes} 分钟内有效,请勿泄露给他人。\n"
        f"如果不是你本人操作,请忽略此邮件。"
    )

    message = MIMEText(body, "plain", "utf-8")
    message["From"] = username
    message["To"] = to_email
    message["Subject"] = Header(subject, "utf-8")

    await aiosmtplib.send(
        message,
        hostname=host,
        port=port,
        username=username,
        password=password,
        start_tls=True,
    )
    logger.info(f"Verification code sent to {to_email}")
