import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_use_tls = settings.SMTP_USE_TLS
        self.email_from = settings.EMAIL_FROM
        self.email_from_name = settings.EMAIL_FROM_NAME

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        is_html: bool = True,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None
    ) -> bool:
        try:
            msg = MIMEMultipart()
            msg['From'] = f"{self.email_from_name} <{self.email_from}>"
            msg['To'] = to_email
            msg['Subject'] = subject

            if cc:
                msg['Cc'] = ', '.join(cc)
            if bcc:
                msg['Bcc'] = ', '.join(bcc)

            if is_html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))

            recipients = [to_email]
            if cc:
                recipients.extend(cc)
            if bcc:
                recipients.extend(bcc)

            context = ssl.create_default_context()
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_use_tls:
                    server.starttls(context=context)
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.email_from, recipients, msg.as_string())

            logger.info(f"Email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False

    async def send_welcome_email(self, user_email: str, username: str) -> bool:
        subject = "Aegis 보안 시스템 회원가입 완료"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #2c3e50; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 30px; background-color: #f8f9fa; }}
                .footer {{ padding: 20px; text-align: center; color: #666; font-size: 12px; }}
                .button {{ display: inline-block; padding: 10px 20px; background-color: #3498db; color: white; text-decoration: none; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Aegis</h1>
                </div>
                <div class="content">
                    <h2>안녕하세요, {username}님!</h2>
                    <p>Aegis에 성공적으로 회원가입이 완료되었습니다.</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="https://aegis.gdgoc.com" class="button">Aegis 서비스 접속하기</a>
                    </div>
                
                    Aegis 팀</p>
                </div>
                <div class="footer">
                    <p>이 메일은 자동으로 발송된 메일입니다. 회신하지 마세요.</p>
                    <p>&copy; 2025 Aegis. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return await self.send_email(user_email, subject, html_body, is_html=True)

    async def send_forgery_detection_email(
        self,
        user_email: str,
        username: str,
        detection_info: dict,
        report_url: str
    ) -> bool:
        subject = "🚨 이미지 위변조 검출 알림"
        
        detection_time = detection_info.get('detection_time', 'N/A')
        image_name = detection_info.get('image_name', 'N/A')
        confidence_score = detection_info.get('confidence_score', 'N/A')
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #e74c3c; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 30px; background-color: #f8f9fa; }}
                .alert-box {{ background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                .info-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                .info-table th, .info-table td {{ padding: 10px; border: 1px solid #ddd; text-align: left; }}
                .info-table th {{ background-color: #f2f2f2; }}
                .footer {{ padding: 20px; text-align: center; color: #666; font-size: 12px; }}
                .button {{ display: inline-block; padding: 12px 25px; background-color: #e74c3c; color: white; text-decoration: none; border-radius: 5px; margin: 10px 0; }}
                .button:hover {{ background-color: #c0392b; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚨 위변조 검출 알림</h1>
                </div>
                <div class="content">
                    <h2>안녕하세요, {username}님</h2>
                    
                    <div class="alert-box">
                        <strong>⚠️ 중요:</strong> 귀하의 이미지에서 위변조가 검출되었습니다.
                    </div>
                    
                    <h3>검출 정보</h3>
                    <table class="info-table">
                        <tr>
                            <th>검출 시간</th>
                            <td>{detection_time}</td>
                        </tr>
                        <tr>
                            <th>이미지명</th>
                            <td>{image_name}</td>
                        </tr>
                        <tr>
                            <th>신뢰도</th>
                            <td>{confidence_score}%</td>
                        </tr>
                    </table>
                    
                    <h3>다음 단계</h3>
                    <ul>
                        <li>아래 링크를 클릭하여 상세 보고서를 확인하세요</li>
                        <li>필요시 추가 보안 조치를 취하시기 바랍니다</li>
                        <li>문의사항이 있으시면 지원팀에 연락해 주세요</li>
                    </ul>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{report_url}" class="button">상세 보고서 보기</a>
                    </div>
                    
                    <p>이 알림은 귀하의 보안을 위해 자동으로 발송되었습니다.</p>
                    
                    <p>감사합니다.<br>
                    Aegis 보안 팀</p>
                </div>
                <div class="footer">
                    <p>이 메일은 자동으로 발송된 메일입니다.</p>
                    <p>문의: support@aegis-security.com</p>
                    <p>&copy; 2024 Aegis Security System. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return await self.send_email(user_email, subject, html_body, is_html=True)


email_service = EmailService()