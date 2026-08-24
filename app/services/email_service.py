import logging
import html
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.core.config import settings

logger = logging.getLogger(__name__)


_COLOR_PRIMARY = "#6366f1"  
_COLOR_TEXT = "#1f2937"  
_COLOR_MUTED = "#6b7280"  
_COLOR_BG = "#f9fafb"  


def _expire_label() -> str:
    minutes = max(1, settings.OTP_EXPIRE_SECONDS // 60)
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


def _build_mime_message(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def _smtp_send(
    host: str,
    port: int,
    to_email: str,
    msg: MIMEMultipart,
    email_type: str,
    *,
    use_tls: bool,
    username: str | None,
    password: str | None,
) -> None:
    with smtplib.SMTP(host, port, timeout=10) as server:
        server.ehlo()
        if use_tls:
            server.starttls()
            server.ehlo()
        if username and password:
            server.login(username, password)
        server.sendmail(settings.SMTP_FROM_EMAIL, to_email, msg.as_string())
    logger.info("%s email sent to %s via %s:%s", email_type, to_email, host, port)


def _send_email(msg: MIMEMultipart, to_email: str, email_type: str) -> None:

    if not settings.SMTP_FROM_EMAIL:
        logger.error(
            "SMTP not configured — cannot send %s email to %s.",
            email_type,
            to_email,
        )
        raise RuntimeError(
            "SMTP is not fully configured. "
            "Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, "
            "SMTP_FROM_EMAIL in your .env file."
        )

    try:
        _smtp_send(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            to_email,
            msg,
            email_type,
            use_tls=settings.SMTP_USE_TLS,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
        )
        return
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning(
            "Primary SMTP failed (%s) for %s: %s — trying Mailpit",
            email_type,
            to_email,
            exc,
        )

    try:
        _smtp_send(
            settings.MAILPIT_HOST,
            settings.MAILPIT_PORT,
            to_email,
            msg,
            email_type,
            use_tls=False,
            username=None,
            password=None,
        )
    except Exception as exc:
        logger.error("Failed to send %s email to %s: %s", email_type, to_email, exc)
        raise RuntimeError(
            "Email could not be sent via the configured SMTP server or Mailpit."
        ) from exc


def _build_email_shell(
    *,
    preheader: str,
    header_icon: str,
    header_title: str,
    body_html: str,
) -> str:
    support_email = settings.SMTP_FROM_EMAIL or ""

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GeoMap</title>
  <style>
    body {{ margin:0; padding:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }}
    a {{ color:{_COLOR_PRIMARY}; text-decoration:none; }}
  </style>
</head>
<body style="margin:0; padding:20px; background-color:{_COLOR_BG};">

  <!-- Preheader -->
  <div style="display:none; max-height:0; overflow:hidden; opacity:0;">
    {html.escape(preheader)}
  </div>

  <!-- Email container -->
  <div style="max-width:560px; margin:0 auto; background:#fff; border-radius:8px; overflow:hidden;">
    
    <!-- Header -->
    <div style="background:{_COLOR_PRIMARY}; color:#fff; padding:32px 24px; text-align:center;">
      <div style="font-size:36px; margin-bottom:8px;">{header_icon}</div>
      <h1 style="margin:0; font-size:20px; font-weight:600;">{header_title}</h1>
    </div>

    <!-- Body -->
    <div style="padding:32px 24px; color:{_COLOR_TEXT}; line-height:1.6;">
      {body_html}
    </div>

    <!-- Footer -->
    <div style="padding:16px 24px; background:{_COLOR_BG}; text-align:center; font-size:12px; color:{_COLOR_MUTED};">
      &copy; 2025 GeoMap &nbsp;&middot;&nbsp;
      <a href="mailto:{support_email}" style="color:{_COLOR_MUTED};">Contact Support</a>
    </div>

  </div>

</body>
</html>"""


def _build_otp_email(to_email: str, full_name: str, otp: str) -> MIMEMultipart:
    safe_name = html.escape(full_name)
    expire_label = _expire_label()

    text_body = (
        f"Hi {safe_name},\n\n"
        f"Your GeoMap verification code is: {otp}\n\n"
        f"This code expires in {expire_label}.\n\n"
        f"If you did not request this code, ignore this email.\n\n"
        f"— The GeoMap Team"
    )

    body_html = f"""\
      <p style="margin:0 0 16px;">Hi <strong>{safe_name}</strong>,</p>
      
      <p style="margin:0 0 24px;">
        To complete your sign-up, enter the verification code below.
        <strong>Do not share it with anyone.</strong>
      </p>

      <!-- OTP Code -->
      <div style="background:{_COLOR_BG}; border-radius:8px; padding:24px; text-align:center; margin:0 0 24px;">
        <div style="font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:2px; color:{_COLOR_MUTED}; margin-bottom:8px;">
          Verification Code
        </div>
        <div style="font-family:'Courier New',monospace; font-size:36px; font-weight:700; letter-spacing:8px; color:{_COLOR_TEXT};">
          {otp}
        </div>
      </div>

      <p style="margin:0 0 16px; padding:12px; background:#fef3c7; border-left:3px solid #f59e0b; border-radius:4px; font-size:14px;">
        ⏱️ This code expires in <strong>{expire_label}</strong>. Request a new one if it expires.
      </p>

      <p style="margin:0; font-size:13px; color:{_COLOR_MUTED};">
        If you didn't request this code, ignore this email — no action is needed.
      </p>"""

    html_body = _build_email_shell(
        preheader=f"Your GeoMap verification code is {otp} — valid for {expire_label}.",
        header_icon="✉️",
        header_title="Verify your account",
        body_html=body_html,
    )

    return _build_mime_message(
        to_email=to_email,
        subject=f"GeoMap – Your verification code: {otp}",
        text_body=text_body,
        html_body=html_body,
    )


def send_otp_email(to_email: str, full_name: str, otp: str) -> None:
    _send_email(_build_otp_email(to_email, full_name, otp), to_email, "OTP")


def _build_reset_email(to_email: str, full_name: str, otp: str) -> MIMEMultipart:
    safe_name = html.escape(full_name)
    expire_label = _expire_label()

    text_body = (
        f"Hi {safe_name},\n\n"
        f"You requested a password reset for your GeoMap account.\n\n"
        f"Your reset code is: {otp}\n\n"
        f"This code expires in {expire_label}.\n\n"
        f"If you did not request a password reset, please ignore this email.\n"
        f"Your password will remain unchanged.\n\n"
        f"— The GeoMap Team"
    )

    body_html = f"""\
      <p style="margin:0 0 16px;">Hi <strong>{safe_name}</strong>,</p>
      
      <p style="margin:0 0 24px;">
        We received a request to reset your GeoMap password.
        Use the code below to set a new one.
      </p>

      <!-- Reset Code -->
      <div style="background:{_COLOR_BG}; border-radius:8px; padding:24px; text-align:center; margin:0 0 24px;">
        <div style="font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:2px; color:{_COLOR_MUTED}; margin-bottom:8px;">
          Reset Code
        </div>
        <div style="font-family:'Courier New',monospace; font-size:36px; font-weight:700; letter-spacing:8px; color:{_COLOR_TEXT};">
          {otp}
        </div>
      </div>

      <p style="margin:0 0 16px; padding:12px; background:#fef3c7; border-left:3px solid #f59e0b; border-radius:4px; font-size:14px;">
        ⏱️ This code expires in <strong>{expire_label}</strong>. Enter it on the reset page to choose a new password.
      </p>

      <p style="margin:0; font-size:13px; color:{_COLOR_MUTED};">
        If you didn't request a password reset, ignore this email — no changes have been made.
      </p>"""

    html_body = _build_email_shell(
        preheader=f"Your GeoMap password reset code is {otp} — valid for {expire_label}.",
        header_icon="🔑",
        header_title="Reset your password",
        body_html=body_html,
    )

    return _build_mime_message(
        to_email=to_email,
        subject="GeoMap – Password reset request",
        text_body=text_body,
        html_body=html_body,
    )


def send_reset_email(to_email: str, full_name: str, otp: str) -> None:
    _send_email(
        _build_reset_email(to_email, full_name, otp), to_email, "password reset"
    )


def _build_payment_confirmation_email(
    to_email: str,
    full_name: str,
    credits_purchased: int,
    new_balance: int,
    amount_inr: int,
) -> MIMEMultipart:
    safe_name = html.escape(full_name)

    text_body = (
        f"Hi {safe_name},\n\n"
        f"Thank you for your purchase!\n\n"
        f"Amount paid   : ₹{amount_inr}\n"
        f"Credits added : +{credits_purchased}\n"
        f"New balance   : {new_balance} credits\n\n"
        f"You can now use your credits for AI chat, place Q&A, and other features.\n\n"
        f"— The GeoMap Team"
    )

    body_html = f"""\
      <p style="margin:0 0 16px;">Hi <strong>{safe_name}</strong>,</p>
      
      <p style="margin:0 0 24px;">
        Your payment was successful and credits have been added to your account.
      </p>

      <!-- Receipt -->
      <div style="background:{_COLOR_BG}; border-radius:8px; padding:20px; margin:0 0 24px;">
        <div style="font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:2px; color:{_COLOR_MUTED}; margin-bottom:16px;">
          Payment Receipt
        </div>
        
        <div style="margin-bottom:12px; padding-bottom:12px; border-bottom:1px solid #e5e7eb;">
          <div style="font-size:13px; color:{_COLOR_MUTED};">Amount paid</div>
          <div style="font-size:20px; font-weight:700; color:{_COLOR_TEXT};">₹{amount_inr}</div>
        </div>
        
        <div style="margin-bottom:12px; padding-bottom:12px; border-bottom:1px solid #e5e7eb;">
          <div style="font-size:13px; color:{_COLOR_MUTED};">Credits purchased</div>
          <div style="font-size:18px; font-weight:700; color:{_COLOR_PRIMARY};">+{credits_purchased}</div>
        </div>
        
        <div>
          <div style="font-size:13px; color:{_COLOR_MUTED};">New balance</div>
          <div style="font-size:22px; font-weight:800; color:{_COLOR_TEXT};">{new_balance} credits</div>
        </div>
      </div>

      <p style="margin:0 0 16px; padding:12px; background:#f0fdf4; border-left:3px solid #22c55e; border-radius:4px; font-size:14px;">
        ✓ Your credits are ready to use for AI chat, place Q&A, and all GeoMap features.
      </p>

      <p style="margin:0; font-size:13px; color:{_COLOR_MUTED};">
        Questions? Contact our support team — we're happy to help.
      </p>"""

    html_body = _build_email_shell(
        preheader=f"Payment confirmed — ₹{amount_inr} · +{credits_purchased} credits added to your account.",
        header_icon="✓",
        header_title="Payment confirmed",
        body_html=body_html,
    )

    return _build_mime_message(
        to_email=to_email,
        subject=f"GeoMap – Payment confirmed · +{credits_purchased} credits",
        text_body=text_body,
        html_body=html_body,
    )


def send_payment_confirmation_email(
    to_email: str,
    full_name: str,
    credits_purchased: int,
    new_balance: int,
    amount_inr: int,
) -> None:
    msg = _build_payment_confirmation_email(
        to_email, full_name, credits_purchased, new_balance, amount_inr
    )
    _send_email(msg, to_email, "payment confirmation")
