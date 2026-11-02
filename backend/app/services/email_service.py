import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.config import settings

logger = logging.getLogger("idevify-email")

class EmailService:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("SMTP_FROM", self.smtp_user or "alerts@idevify.com")
        self.resend_api_key = os.getenv("RESEND_API_KEY", "")

    async def send_ticket_alert(
        self,
        to_email: str,
        business_name: str,
        ticket_number: str,
        customer_contact: str,
        channel: str,
        question_text: str,
        priority: str = "medium"
    ) -> bool:
        """Sends an urgent email notification to the business owner about a new ticket."""
        subject = f"[{priority.upper()}] New Support Ticket {ticket_number} - {business_name}"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f8fafc; color: #1e293b; padding: 20px; }}
            .container {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }}
            .header {{ background: linear-gradient(135deg, #4f46e5, #7c3aed); color: #ffffff; padding: 24px; text-align: center; }}
            .header h1 {{ margin: 0; font-size: 20px; font-weight: 700; }}
            .content {{ padding: 24px; }}
            .badge {{ display: inline-block; padding: 4px 10px; font-size: 12px; font-weight: 600; border-radius: 9999px; background: #fef3c7; color: #d97706; text-transform: uppercase; }}
            .badge-urgent {{ background: #fee2e2; color: #dc2626; }}
            .card {{ background: #f1f5f9; border-radius: 8px; padding: 16px; margin: 16px 0; border-left: 4px solid #4f46e5; }}
            .meta {{ font-size: 13px; color: #64748b; margin-bottom: 8px; }}
            .btn {{ display: inline-block; background: #4f46e5; color: #ffffff !important; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; font-size: 14px; margin-top: 16px; text-align: center; }}
            .footer {{ font-size: 12px; color: #94a3b8; text-align: center; padding: 16px; border-top: 1px solid #e2e8f0; }}
          </style>
        </head>
        <body>
          <div class="container">
            <div class="header">
              <h1>Iveri AI Customer Support</h1>
            </div>
            <div class="content">
              <span class="badge {'badge-urgent' if priority == 'urgent' else ''}">{priority} Priority</span>
              <h2 style="font-size: 18px; margin-top: 12px;">New Support Ticket: {ticket_number}</h2>
              <div class="meta">
                <strong>Business:</strong> {business_name}<br>
                <strong>Channel:</strong> {channel.upper()}<br>
                <strong>Customer Contact:</strong> {customer_contact or 'Anonymous / In-Chat'}
              </div>
              <div class="card">
                <strong>Customer Query / Request:</strong>
                <p style="margin: 8px 0 0 0; font-style: italic;">"{question_text}"</p>
              </div>
              <p style="font-size: 14px; color: #475569;">
                Our AI assistant could not find a confirmed answer in your knowledge base or the customer requested human assistance.
              </p>
              <center>
                <a href="https://idevify.onrender.com/dashboard" class="btn">Answer & Resolve in Dashboard</a>
              </center>
            </div>
            <div class="footer">
              &copy; Iveri AI Customer Support Assistant for {business_name}. All rights reserved.
            </div>
          </div>
        </body>
        </html>
        """

        # In testing or unconfigured mode, safely mock output
        if settings.ENVIRONMENT == "testing" or (not self.smtp_user and not self.resend_api_key):
            logger.info(f"[EMAIL_ALERT_DISPATCH_MOCK] To: {to_email} | Subject: {subject} | Ticket: {ticket_number}")
            return True

        # Send via SMTP
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, [to_email], msg.as_string())
            logger.info(f"Successfully dispatched email alert for ticket {ticket_number} to {to_email}")
            return True
        except Exception as e:
            logger.warning(f"Failed to deliver SMTP email alert: {e}. Logged ticket {ticket_number} locally.")
            return False

email_service = EmailService()
