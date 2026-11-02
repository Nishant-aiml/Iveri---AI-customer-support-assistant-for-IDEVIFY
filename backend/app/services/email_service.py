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

    async def _dispatch_email(self, to_email: str, subject: str, html_body: str, ticket_number: str = "") -> bool:
        """Internal helper to dispatch emails via SMTP or gracefully mock in testing/dev."""
        if not to_email or "@" not in to_email:
            return False

        # In testing or unconfigured mode, safely mock output
        if settings.ENVIRONMENT == "testing" or (not self.smtp_user and not self.resend_api_key):
            logger.info(f"[EMAIL_DISPATCH_MOCK] To: {to_email} | Subject: {subject} | Ticket: {ticket_number}")
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
            logger.info(f"Successfully dispatched email for ticket {ticket_number} to {to_email}")
            return True
        except Exception as e:
            logger.warning(f"Failed to deliver SMTP email: {e}. Target: {to_email}")
            return False

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
        return await self._dispatch_email(to_email, subject, html_body, ticket_number)

    async def send_customer_ticket_acknowledgment(
        self,
        to_email: str,
        business_name: str,
        ticket_number: str,
        customer_name: str | None = None,
        question_text: str | None = None
    ) -> bool:
        """Sends an acknowledgment email to the customer confirming their ticket or callback was received."""
        name_greeting = f" {customer_name}" if customer_name else ""
        subject = f"We've received your request (Ticket #{ticket_number}) - {business_name}"
        query_snippet = f"""
        <div style="background: #f8fafc; border-radius: 8px; padding: 14px; margin: 14px 0; border-left: 4px solid #2563eb;">
          <strong style="color: #1e293b; font-size: 13px;">Your Request:</strong>
          <p style="margin: 6px 0 0 0; color: #475569; font-style: italic; font-size: 14px;">"{question_text}"</p>
        </div>
        """ if question_text else ""

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f8fafc; color: #1e293b; padding: 20px; }}
            .container {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }}
            .header {{ background: linear-gradient(135deg, #2563eb, #1d4ed8); color: #ffffff; padding: 24px; text-align: center; }}
            .header h1 {{ margin: 0; font-size: 20px; font-weight: 700; }}
            .content {{ padding: 24px; }}
            .badge {{ display: inline-block; padding: 4px 10px; font-size: 12px; font-weight: 600; border-radius: 9999px; background: #dbeafe; color: #1e40af; text-transform: uppercase; }}
            .footer {{ font-size: 12px; color: #94a3b8; text-align: center; padding: 16px; border-top: 1px solid #e2e8f0; }}
          </style>
        </head>
        <body>
          <div class="container">
            <div class="header">
              <h1>{business_name}</h1>
            </div>
            <div class="content">
              <span class="badge">Ticket Received</span>
              <h2 style="font-size: 18px; margin-top: 12px;">Hi{name_greeting}, we've received your request!</h2>
              <p style="font-size: 14px; color: #475569; line-height: 1.6;">
                Thank you for contacting <strong>{business_name}</strong>. Your inquiry has been registered as Ticket <strong>#{ticket_number}</strong>. Our support team is actively reviewing it and will get back to you shortly.
              </p>
              {query_snippet}
              <p style="font-size: 14px; color: #64748b; margin-top: 16px;">
                You don't need to do anything else. We will email you right here as soon as our team has an update for you.
              </p>
            </div>
            <div class="footer">
              &copy; {business_name} Customer Care &bull; Ticket #{ticket_number}
            </div>
          </div>
        </body>
        </html>
        """
        return await self._dispatch_email(to_email, subject, html_body, ticket_number)

    async def send_customer_ticket_resolved(
        self,
        to_email: str,
        business_name: str,
        ticket_number: str,
        question_text: str,
        resolved_answer: str,
        customer_name: str | None = None
    ) -> bool:
        """Sends the verified resolution answer to the customer's email address."""
        name_greeting = f" {customer_name}" if customer_name else ""
        subject = f"Resolution Update: Ticket #{ticket_number} - {business_name}"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f8fafc; color: #1e293b; padding: 20px; }}
            .container {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }}
            .header {{ background: linear-gradient(135deg, #10b981, #059669); color: #ffffff; padding: 24px; text-align: center; }}
            .header h1 {{ margin: 0; font-size: 20px; font-weight: 700; }}
            .content {{ padding: 24px; }}
            .badge {{ display: inline-block; padding: 4px 10px; font-size: 12px; font-weight: 600; border-radius: 9999px; background: #d1fae5; color: #065f46; text-transform: uppercase; }}
            .question-box {{ background: #f8fafc; border-radius: 8px; padding: 12px; margin: 14px 0; border: 1px solid #e2e8f0; }}
            .answer-card {{ background: #f0fdf4; border-radius: 8px; padding: 16px; margin: 16px 0; border-left: 4px solid #10b981; }}
            .footer {{ font-size: 12px; color: #94a3b8; text-align: center; padding: 16px; border-top: 1px solid #e2e8f0; }}
          </style>
        </head>
        <body>
          <div class="container">
            <div class="header">
              <h1>{business_name}</h1>
            </div>
            <div class="content">
              <span class="badge">Resolved</span>
              <h2 style="font-size: 18px; margin-top: 12px;">Hi{name_greeting}, your inquiry has been answered!</h2>
              
              <div class="question-box">
                <span style="font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase;">Your Question</span>
                <p style="margin: 4px 0 0 0; color: #334155; font-size: 14px; font-style: italic;">"{question_text}"</p>
              </div>

              <div class="answer-card">
                <span style="font-size: 11px; color: #065f46; font-weight: 700; text-transform: uppercase;">Verified Answer</span>
                <p style="margin: 6px 0 0 0; color: #1e293b; font-size: 15px; line-height: 1.6; font-weight: 500;">{resolved_answer}</p>
              </div>

              <p style="font-size: 14px; color: #64748b; margin-top: 16px;">
                Thank you for your patience! If you have any further questions, feel free to reply directly to this email or visit our website.
              </p>
            </div>
            <div class="footer">
              &copy; {business_name} Customer Care &bull; Ticket #{ticket_number}
            </div>
          </div>
        </body>
        </html>
        """
        return await self._dispatch_email(to_email, subject, html_body, ticket_number)

email_service = EmailService()
