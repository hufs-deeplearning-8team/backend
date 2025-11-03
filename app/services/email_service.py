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
        self.frontend_base_url = settings.FRONTEND_BASE_URL.rstrip('/')
    
    def _build_frontend_url(self, path: str = "") -> str:
        if not path:
            return self.frontend_base_url
        normalized = path.lstrip("/")
        return f"{self.frontend_base_url}/{normalized}"
    
    async def check_email_service_status(self) -> dict:
        """이메일 서비스 상태 확인"""
        status = {
            "email_configured": False,
            "smtp_connection": False,
            "error": None
        }
        
        try:
            # 이메일 설정 확인
            if not all([self.smtp_host, self.smtp_port, self.smtp_user, self.smtp_password, self.email_from]):
                status["error"] = "이메일 설정이 완전하지 않습니다"
                logger.warning("❌ 이메일 설정 불완전")
                return status
            
            status["email_configured"] = True
            logger.info("✅ 이메일 설정 확인됨")
            
            # SMTP 연결 테스트
            context = ssl.create_default_context()
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            
            if self.smtp_use_tls:
                server.starttls(context=context)
            
            server.login(self.smtp_user, self.smtp_password)
            server.quit()
            
            status["smtp_connection"] = True
            logger.info("✅ SMTP 서버 연결 성공")
            
        except Exception as e:
            status["error"] = str(e)
            logger.error(f"❌ 이메일 서비스 확인 실패: {e}")
        
        return status

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
        subject = "🎉 Aegis 회원가입을 축하합니다!"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                body {{
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    line-height: 1.6;
                    color: #1a1a1a;
                    background: #0a0a0a;
                    padding: 20px;
                }}
                .email-container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: #ffffff;
                    border-radius: 24px;
                    overflow: hidden;
                    border: 1px solid #e2e8f0;
                    box-shadow: 0 20px 60px rgba(59, 130, 246, 0.1);
                }}
                .header {{
                    background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
                    padding: 60px 40px;
                    text-align: center;
                    border-bottom: 1px solid #e2e8f0;
                    position: relative;
                }}
                .header::before {{
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="welcome" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="10" cy="10" r="1" fill="white" opacity="0.1"/><circle cx="5" cy="15" r="0.5" fill="white" opacity="0.05"/></pattern></defs><rect width="100" height="100" fill="url(%23welcome)"/></svg>');
                }}
                .logo-container {{
                    margin-bottom: 24px;
                }}
                .logo {{
                    height: 80px;
                    width: auto;
                    filter: brightness(0) invert(1);
                    position: relative;
                    z-index: 1;
                }}
                .header-title {{
                    font-size: 32px;
                    font-weight: 700;
                    color: #ffffff;
                    margin-bottom: 12px;
                    letter-spacing: -0.02em;
                    position: relative;
                    z-index: 1;
                }}
                .header-subtitle {{
                    font-size: 18px;
                    color: #dbeafe;
                    font-weight: 400;
                    position: relative;
                    z-index: 1;
                }}
                .content {{
                    padding: 60px 40px;
                    background: #ffffff;
                }}
                .welcome-message {{
                    text-align: center;
                    margin-bottom: 48px;
                }}
                .welcome-title {{
                    font-size: 28px;
                    font-weight: 600;
                    color: #1e293b;
                    margin-bottom: 16px;
                    letter-spacing: -0.01em;
                }}
                .welcome-subtitle {{
                    font-size: 16px;
                    color: #64748b;
                    line-height: 1.5;
                }}
                .features-section {{
                    margin: 48px 0;
                }}
                .features-title {{
                    font-size: 20px;
                    font-weight: 600;
                    color: #1e293b;
                    text-align: center;
                    margin-bottom: 32px;
                }}
                .features-grid {{
                    display: flex;
                    gap: 16px;
                    justify-content: center;
                    flex-wrap: wrap;
                }}
                .feature-item {{
                    background: #ffffff;
                    border: 1px solid #e2e8f0;
                    border-radius: 20px;
                    padding: 32px 24px;
                    text-align: center;
                    transition: all 0.3s ease;
                    width: 280px;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
                }}
                .feature-item.thunder {{
                    background: #ffffff;
                }}
                .feature-item.siren {{
                    background: linear-gradient(135deg, #4c51bf 0%, #667eea 100%);
                    color: white;
                }}
                .feature-item.siren .feature-title,
                .feature-item.siren .feature-subtitle,
                .feature-item.siren .feature-desc {{
                    color: white;
                }}
                .feature-item.lock {{
                    background: #ffffff;
                }}
                .feature-item:hover {{
                    transform: translateY(-4px);
                    box-shadow: 0 12px 24px rgba(0, 0, 0, 0.1);
                }}
                .feature-icon {{
                    font-size: 48px;
                    margin-bottom: 20px;
                    display: block;
                    color: #4c51bf;
                }}
                .feature-item.siren .feature-icon {{
                    color: white;
                }}
                .feature-title {{
                    font-size: 18px;
                    font-weight: 700;
                    color: #1a202c;
                    margin-bottom: 8px;
                }}
                .feature-subtitle {{
                    font-size: 14px;
                    font-weight: 600;
                    color: #4c51bf;
                    margin-bottom: 16px;
                }}
                .feature-desc {{
                    font-size: 13px;
                    color: #4a5568;
                    line-height: 1.5;
                }}
                .cta-section {{
                    text-align: center;
                    margin: 48px 0;
                    padding: 32px;
                    background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
                    border: 1px solid #3b82f6;
                    border-radius: 16px;
                }}
                .cta-title {{
                    font-size: 18px;
                    font-weight: 600;
                    color: #1e293b;
                    margin-bottom: 20px;
                }}
                .cta-button {{
                    display: inline-block;
                    padding: 14px 32px;
                    background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
                    color: #ffffff !important;
                    text-decoration: none;
                    border-radius: 12px;
                    font-weight: 600;
                    font-size: 14px;
                    transition: all 0.3s ease;
                    box-shadow: 0 4px 15px rgba(59, 130, 246, 0.3);
                }}
                .cta-button:hover {{
                    background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%);
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(59, 130, 246, 0.4);
                }}
                .footer {{
                    padding: 32px 40px;
                    background: #f8fafc;
                    text-align: center;
                    border-top: 1px solid #e2e8f0;
                }}
                .footer-text {{
                    font-size: 12px;
                    color: #64748b;
                    margin-bottom: 8px;
                }}
                .copyright {{
                    font-size: 12px;
                    color: #94a3b8;
                }}
                @media (max-width: 600px) {{
                    .features-grid {{
                        grid-template-columns: 1fr;
                    }}
                    .content {{
                        padding: 40px 24px;
                    }}
                    .header {{
                        padding: 40px 24px;
                    }}
                    .footer {{
                        padding: 24px 24px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <div class="logo-container">
                        <img src="https://aegis.gdgoc.com/AEGIS.png" alt="Aegis Logo" class="logo" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                        <div style="display: none; font-size: 32px; font-weight: 700; color: #ffffff;">AEGIS</div>
                    </div>
                    <h1 class="header-title">환영합니다!</h1>
                    <p class="header-subtitle">이미지 보안의 새로운 기준</p>
                </div>
                
                <div class="content">
                    <div class="welcome-message">
                        <h2 class="welcome-title">{username}님, 가입을 축하드립니다! 🎉</h2>
                        <p class="welcome-subtitle">
                            Aegis에 성공적으로 가입하셨습니다.<br>
                            최첨단 AI로 이미지 보안을 강화하세요.
                        </p>
                    </div>
                    
                    <div class="cta-section">
                        <h3 class="cta-title">지금 바로 Aegis를 체험해보세요</h3>
                        <a href="{self._build_frontend_url()}" class="cta-button">
                            Aegis 시작하기
                        </a>
                    </div>
                    
                    <div class="features-section">
                        <h3 class="features-title">Aegis 핵심 기능</h3>
                        <div class="features-grid">
                            <div class="feature-item thunder">
                                <div class="feature-icon">⚡</div>
                                <div class="feature-title">신종 AI 공격 즉시 대응</div>
                                <div class="feature-subtitle">Zero-shot 학습 방식</div>
                                <div class="feature-desc">특정 공격 유형을 학습할 필요 없이, 알려지지 않은 새로운 AI 편집 기술에 즉시 대응 가능</div>
                            </div>
                            <div class="feature-item siren">
                                <div class="feature-icon">🚨</div>
                                <div class="feature-title">자동화된 불법 유출 및<br>위변조 감시</div>
                                <div class="feature-subtitle">능동적 모니터링 시스템</div>
                                <div class="feature-desc">제3자가 위변조된 이미지 검증 시, 원본 소유자에게 알려져, 내가 모르는 사이에 일어난 위변조 파악 가능</div>
                            </div>
                            <div class="feature-item lock">
                                <div class="feature-icon">🔒</div>
                                <div class="feature-title">딥러닝 기반 강력한 내구성</div>
                                <div class="feature-subtitle">워터마크 생존력</div>
                                <div class="feature-desc">압축, 왜곡 등 일반적인 이미지 처리 과정에서도 워터마크가 강력하게 유지되어, 콘텐츠의 원본 가치를 안전하게 보호</div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="footer">
                    <p class="footer-text">이 메일은 자동으로 발송된 메일입니다. 회신하지 마세요.</p>
                    <p class="copyright">&copy; 2025 Aegis. All rights reserved.</p>
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
        report_url: str,
        image_url: str = None,
        original_image_info: dict = None
    ) -> bool:
        
        detection_time = detection_info.get('detection_time', 'N/A')
        image_name = detection_info.get('image_name', 'N/A')
        confidence_score = detection_info.get('confidence_score', 'N/A')
        detection_method = detection_info.get('detection_method', 'AI 분석')
        
        # RobustWide인 경우 변조률 표시 처리
        if detection_method == 'RobustWide':
            confidence_display = '변조률 지원안함'
        else:
            confidence_display = f'{confidence_score}%'
        
        # 원본 이미지 정보
        original_info = original_image_info or {}
        original_image_id = original_info.get('image_id', 'N/A')
        original_filename = original_info.get('filename', 'N/A')
        upload_time = original_info.get('upload_time', 'N/A')
        copyright_info = original_info.get('copyright_info', '저작권자 정보 없음')
        watermark_image_url = original_info.get('watermark_image_url', '')
        
        # 이메일 제목에 이미지 번호 포함
        subject = f"🚨 [긴급] 이미지 #{original_image_id} 위변조 검출 알림"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                body {{
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    line-height: 1.6;
                    color: #1a1a1a;
                    background: #0a0a0a;
                    padding: 20px;
                }}
                .email-container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: #111111;
                    border-radius: 24px;
                    overflow: hidden;
                    border: 2px solid #dc2626;
                }}
                .header {{
                    background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
                    padding: 40px 40px;
                    text-align: center;
                    position: relative;
                }}
                .header::before {{
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="warning" width="20" height="20" patternUnits="userSpaceOnUse"><polygon points="10,2 18,16 2,16" fill="none" stroke="white" stroke-width="0.5" opacity="0.1"/></pattern></defs><rect width="100" height="100" fill="url(%23warning)"/></svg>');
                }}
                .logo-container {{
                    margin-bottom: 20px;
                    position: relative;
                    z-index: 1;
                }}
                .logo {{
                    height: 60px;
                    width: auto;
                    filter: brightness(0) invert(1);
                }}
                .alert-icon {{
                    font-size: 48px;
                    margin-bottom: 16px;
                    display: block;
                    position: relative;
                    z-index: 1;
                }}
                .header-title {{
                    font-size: 28px;
                    font-weight: 700;
                    color: #ffffff;
                    margin-bottom: 8px;
                    letter-spacing: -0.01em;
                    position: relative;
                    z-index: 1;
                }}
                .header-subtitle {{
                    font-size: 16px;
                    color: #fecaca;
                    font-weight: 400;
                    position: relative;
                    z-index: 1;
                }}
                .content {{
                    padding: 40px 40px;
                    background: #111111;
                }}
                .alert-section {{
                    background: #1a1a1a;
                    border: 2px solid #dc2626;
                    border-radius: 16px;
                    padding: 24px;
                    margin-bottom: 32px;
                    text-align: center;
                }}
                .alert-title {{
                    font-size: 20px;
                    font-weight: 600;
                    color: #dc2626;
                    margin-bottom: 12px;
                }}
                .alert-message {{
                    font-size: 16px;
                    color: #ffffff;
                    line-height: 1.5;
                }}
                .user-greeting {{
                    font-size: 18px;
                    color: #ffffff;
                    margin-bottom: 24px;
                }}
                .detection-details {{
                    background: #1a1a1a;
                    border: 1px solid #333333;
                    border-radius: 16px;
                    padding: 24px;
                    margin: 24px 0;
                }}
                .details-title {{
                    font-size: 18px;
                    font-weight: 600;
                    color: #ffffff;
                    margin-bottom: 20px;
                    text-align: center;
                }}
                .details-table {{
                    width: 100%;
                    border-collapse: collapse;
                    background: transparent;
                }}
                .details-table tr {{
                    border-bottom: 1px solid #222222;
                }}
                .details-table tr:last-child {{
                    border-bottom: none;
                }}
                .details-table td {{
                    padding: 16px 0;
                    vertical-align: top;
                    background: transparent;
                }}
                .detail-label {{
                    font-size: 13px;
                    color: #888888;
                    font-weight: 500;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    padding-bottom: 8px;
                    display: block;
                }}
                .detail-value {{
                    font-size: 15px;
                    color: #ffffff;
                    font-weight: 600;
                    line-height: 1.4;
                }}
                .threat-high {{
                    color: #dc2626;
                }}
                .image-preview {{
                    text-align: center;
                    margin: 24px 0;
                    background: #1a1a1a;
                    border: 1px solid #333333;
                    border-radius: 16px;
                    padding: 24px;
                }}
                .image-preview img {{
                    max-width: 300px;
                    height: auto;
                    border-radius: 8px;
                    border: 2px solid #dc2626;
                }}
                .image-caption {{
                    font-size: 12px;
                    color: #888888;
                    margin-top: 12px;
                }}
                .action-title {{
                    font-size: 18px;
                    font-weight: 600;
                    color: #ffffff;
                    margin-bottom: 16px;
                }}
                .action-list {{
                    text-align: left;
                    margin: 16px 0;
                }}
                .action-list li {{
                    color: #cccccc;
                    margin-bottom: 8px;
                    font-size: 14px;
                }}
                .btn-secondary {{
                    display: inline-block;
                    padding: 14px 24px;
                    background: #ffffff;
                    color: #000000;
                    text-decoration: none;
                    border-radius: 12px;
                    font-weight: 500;
                    font-size: 14px;
                    transition: all 0.3s ease;
                    margin: 8px;
                }}
                .btn-secondary:hover {{
                    background: #f0f0f0;
                    transform: translateY(-1px);
                }}
                .action-section {{
                    background: #1a1a1a;
                    border: 1px solid #333333;
                    border-radius: 16px;
                    padding: 24px;
                    margin: 24px 0;
                    text-align: center;
                }}
                .cta-buttons {{
                    display: flex;
                    gap: 16px;
                    justify-content: center;
                    margin: 24px 0;
                    flex-wrap: wrap;
                    text-align: center;
                }}
                .security-notice {{
                    background: #0f172a;
                    border: 1px solid #1e293b;
                    border-radius: 12px;
                    padding: 20px;
                    margin: 24px 0;
                }}
                .security-notice p {{
                    color: #94a3b8;
                    font-size: 14px;
                    margin-bottom: 8px;
                }}
                .footer {{
                    padding: 32px 40px;
                    background: #0a0a0a;
                    text-align: center;
                    border-top: 1px solid #222222;
                }}
                .footer-text {{
                    font-size: 12px;
                    color: #666666;
                    margin-bottom: 8px;
                }}
                .copyright {{
                    font-size: 12px;
                    color: #444444;
                }}
                @media (max-width: 600px) {{
                    .content {{
                        padding: 24px 20px;
                    }}
                    .header {{
                        padding: 24px 20px;
                    }}
                    .cta-buttons {{
                        flex-direction: column;
                    }}
                    .footer {{
                        padding: 24px 20px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <div class="logo-container">
                        <img src="https://aegis.gdgoc.com/AEGIS.png" alt="Aegis Logo" class="logo" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                        <div style="display: none; font-size: 24px; font-weight: 700; color: #ffffff;">AEGIS</div>
                    </div>
                    <span class="alert-icon">🚨</span>
                    <h1 class="header-title">위변조 이미지 검출</h1>
                    <p class="header-subtitle">보안 위협이 감지되었습니다</p>
                </div>
                
                <div class="content">
                    <p class="user-greeting">안녕하세요, {username}님</p>
                    
                    <div class="alert-section">
                        <h2 class="alert-title">⚠️ 긴급 보안 알림</h2>
                        <p class="alert-message">
                            귀하의 이미지에서 위변조가 검출되었습니다.<br>
                            즉시 확인이 필요합니다.
                        </p>
                    </div>
                    
                    <div class="detection-details">
                        <h3 class="details-title">검출 상세 정보</h3>
                        <table class="details-table">
                            <tr>
                                <td>
                                    <span class="detail-label">검출 시간</span>
                                    <span class="detail-value">{detection_time}</span>
                                </td>
                            </tr>
                            <tr>
                                <td>
                                    <span class="detail-label">이미지 파일명</span>
                                    <span class="detail-value">{image_name}</span>
                                </td>
                            </tr>
                            <tr>
                                <td>
                                    <span class="detail-label">변조률</span>
                                    <span class="detail-value threat-high">{confidence_display}</span>
                                </td>
                            </tr>
                            <tr>
                                <td>
                                    <span class="detail-label">검출 방법</span>
                                    <span class="detail-value">{detection_method}</span>
                                </td>
                            </tr>
                            {"<tr><td style='padding-top: 24px; text-align: center;'><span class='detail-label' style='display: block; margin-bottom: 16px;'>검출된 위변조 이미지</span><img src='" + image_url + "' alt='검출된 위변조 이미지' style='max-width: 300px; height: auto; border-radius: 8px; border: 2px solid #dc2626; display: block; margin: 0 auto;'><p style='color: #888; font-size: 12px; margin-top: 8px;'>※ 위변조 이미지</p></td></tr>" if image_url else ""}
                        </table>
                    </div>
                    
                    <div class="detection-details">
                        <h3 class="details-title">보호된 원본 이미지 정보</h3>
                        <table class="details-table">
                            <tr>
                                <td>
                                    <span class="detail-label">이미지 ID</span>
                                    <span class="detail-value">{original_image_id}</span>
                                </td>
                            </tr>
                            <tr>
                                <td>
                                    <span class="detail-label">원본 파일명</span>
                                    <span class="detail-value">{original_filename}</span>
                                </td>
                            </tr>
                            <tr>
                                <td>
                                    <span class="detail-label">업로드 시간</span>
                                    <span class="detail-value">{upload_time}</span>
                                </td>
                            </tr>
                            <tr>
                                <td>
                                    <span class="detail-label">저작권 정보</span>
                                    <span class="detail-value">{copyright_info}</span>
                                </td>
                            </tr>
                        </table>
                        
                        <div style="margin-top: 24px; text-align: center;">
                            <h4 style="color: #ffffff; margin-bottom: 16px;">워터마크 이미지</h4>
                            <div style="justify-content: center; align-items: center;">
                                {"<div style='text-align: center;'><img src='" + watermark_image_url + "' alt='워터마크 이미지' style='max-width: 300px; height: auto; border-radius: 8px; border: 2px solid #3b82f6; display: block; margin: 0 auto;'><p style='color: #888; font-size: 12px; margin-top: 8px;'>워터마크</p></div>" if watermark_image_url else ""}
                            </div>
                        </div>
                    </div>
                    
                    <div class="action-section">
                        <h3 class="action-title">상세 정보 확인</h3>
                        
                        <div class="cta-buttons">
                            <a href="{report_url}" class="btn-secondary">
                                📊 상세 보고서 확인
                            </a>
                            <a href="mailto:kisiaaegis@gmail.com?subject=위변조%20검출%20문의&body=안녕하세요.%20위변조%20검출에%20관련하여%20문의드립니다." class="btn-secondary">
                                💬 지원팀 문의
                            </a>
                        </div>
                    </div>
                    
                </div>
                
                <div class="footer">
                    <p class="footer-text">이 메일은 보안 위협 감지 시 자동으로 발송된 메일입니다.</p>
                    <p class="footer-text">문의: kisiaaegis@gmail.com</p>
                    <p class="copyright">&copy; 2025 Aegis Security System. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return await self.send_email(user_email, subject, html_body, is_html=True)

    async def send_original_confirmation_email(
        self,
        user_email: str,
        username: str,
        confirmation_info: dict,
        report_url: str,
        image_url: str = None,
        original_image_info: dict = None
    ) -> bool:
        """원본 확인 시 원저작자에게 알림 이메일 발송"""
        
        confirmation_time = confirmation_info.get('confirmation_time', 'N/A')
        image_name = confirmation_info.get('image_name', 'N/A')
        image_number = confirmation_info.get('image_number', 'N/A')
        verification_method = confirmation_info.get('verification_method', 'AI 분석')
        
        # 원본 이미지 정보
        original_info = original_image_info or {}
        original_image_id = original_info.get('image_id', 'N/A')
        original_filename = original_info.get('filename', 'N/A')
        upload_time = original_info.get('upload_time', 'N/A')
        copyright_info = original_info.get('copyright_info', '저작권자 정보 없음')
        watermark_image_url = original_info.get('watermark_image_url', '')
        
        # 이메일 제목에 이미지 번호 포함
        subject = f"✅ [알림] 이미지 #{original_image_id} 원본 확인 알림"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                body {{
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    line-height: 1.6;
                    color: #1a1a1a;
                    background: #0a0a0a;
                    padding: 20px;
                }}
                .email-container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: #ffffff;
                    border-radius: 24px;
                    overflow: hidden;
                    border: 2px solid #10b981;
                    box-shadow: 0 20px 60px rgba(16, 185, 129, 0.1);
                }}
                .header {{
                    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                    padding: 40px 40px;
                    text-align: center;
                    position: relative;
                }}
                .header::before {{
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="success" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="10" cy="10" r="2" fill="white" opacity="0.1"/><path d="M6,10 L9,13 L14,8" stroke="white" stroke-width="0.5" fill="none" opacity="0.1"/></pattern></defs><rect width="100" height="100" fill="url(%23success)"/></svg>');
                }}
                .logo-container {{
                    margin-bottom: 20px;
                    position: relative;
                    z-index: 1;
                }}
                .logo {{
                    height: 60px;
                    width: auto;
                    filter: brightness(0) invert(1);
                }}
                .success-icon {{
                    font-size: 48px;
                    margin-bottom: 16px;
                    display: block;
                    position: relative;
                    z-index: 1;
                }}
                .header-title {{
                    font-size: 28px;
                    font-weight: 700;
                    color: #ffffff;
                    margin-bottom: 8px;
                    letter-spacing: -0.01em;
                    position: relative;
                    z-index: 1;
                }}
                .header-subtitle {{
                    font-size: 16px;
                    color: #d1fae5;
                    font-weight: 400;
                    position: relative;
                    z-index: 1;
                }}
                .content {{
                    padding: 40px 40px;
                    background: #ffffff;
                }}
                .success-section {{
                    background: #f0fdf4;
                    border: 2px solid #10b981;
                    border-radius: 16px;
                    padding: 24px;
                    margin-bottom: 32px;
                    text-align: center;
                }}
                .success-title {{
                    font-size: 20px;
                    font-weight: 600;
                    color: #10b981;
                    margin-bottom: 12px;
                }}
                .success-message {{
                    font-size: 16px;
                    color: #166534;
                    line-height: 1.5;
                }}
                .user-greeting {{
                    font-size: 18px;
                    color: #1f2937;
                    margin-bottom: 24px;
                }}
                .confirmation-details {{
                    background: #f9fafb;
                    border: 1px solid #e5e7eb;
                    border-radius: 16px;
                    padding: 24px;
                    margin: 24px 0;
                }}
                .details-title {{
                    font-size: 18px;
                    font-weight: 600;
                    color: #1f2937;
                    margin-bottom: 20px;
                    text-align: center;
                }}
                .details-table {{
                    width: 100%;
                    border-collapse: collapse;
                    background: transparent;
                }}
                .details-table tr {{
                    border-bottom: 1px solid #e5e7eb;
                }}
                .details-table tr:last-child {{
                    border-bottom: none;
                }}
                .details-table td {{
                    padding: 16px 0;
                    vertical-align: top;
                    background: transparent;
                }}
                .detail-label {{
                    font-size: 13px;
                    color: #6b7280;
                    font-weight: 500;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    padding-bottom: 8px;
                    display: block;
                }}
                .detail-value {{
                    font-size: 15px;
                    color: #1f2937;
                    font-weight: 600;
                    line-height: 1.4;
                }}
                .status-confirmed {{
                    color: #10b981;
                }}
                .image-preview {{
                    text-align: center;
                    margin: 24px 0;
                    background: #f9fafb;
                    border: 1px solid #e5e7eb;
                    border-radius: 16px;
                    padding: 24px;
                }}
                .image-preview img {{
                    max-width: 300px;
                    height: auto;
                    border-radius: 8px;
                    border: 2px solid #10b981;
                }}
                .image-caption {{
                    font-size: 12px;
                    color: #6b7280;
                    margin-top: 12px;
                }}
                .action-title {{
                    font-size: 18px;
                    font-weight: 600;
                    color: #1f2937;
                    margin-bottom: 16px;
                }}
                .btn-primary {{
                    display: inline-block;
                    padding: 14px 24px;
                    background: #10b981;
                    color: #ffffff;
                    text-decoration: none;
                    border-radius: 12px;
                    font-weight: 500;
                    font-size: 14px;
                    transition: all 0.3s ease;
                    margin: 8px;
                }}
                .btn-primary:hover {{
                    background: #059669;
                    transform: translateY(-1px);
                }}
                .btn-secondary {{
                    display: inline-block;
                    padding: 14px 24px;
                    background: #ffffff;
                    color: #374151;
                    text-decoration: none;
                    border: 1px solid #d1d5db;
                    border-radius: 12px;
                    font-weight: 500;
                    font-size: 14px;
                    transition: all 0.3s ease;
                    margin: 8px;
                }}
                .btn-secondary:hover {{
                    background: #f9fafb;
                    transform: translateY(-1px);
                }}
                .action-section {{
                    background: #f9fafb;
                    border: 1px solid #e5e7eb;
                    border-radius: 16px;
                    padding: 24px;
                    margin: 24px 0;
                    text-align: center;
                }}
                .cta-buttons {{
                    display: flex;
                    gap: 16px;
                    justify-content: center;
                    margin: 24px 0;
                    flex-wrap: wrap;
                    text-align: center;
                }}
                .security-notice {{
                    background: #f0fdf4;
                    border: 1px solid #d1fae5;
                    border-radius: 12px;
                    padding: 20px;
                    margin: 24px 0;
                }}
                .security-notice p {{
                    color: #166534;
                    font-size: 14px;
                    margin-bottom: 8px;
                }}
                .footer {{
                    padding: 32px 40px;
                    background: #f9fafb;
                    text-align: center;
                    border-top: 1px solid #e5e7eb;
                }}
                .footer-text {{
                    font-size: 12px;
                    color: #6b7280;
                    margin-bottom: 8px;
                }}
                .copyright {{
                    font-size: 12px;
                    color: #9ca3af;
                }}
                @media (max-width: 600px) {{
                    .content {{
                        padding: 24px 20px;
                    }}
                    .header {{
                        padding: 24px 20px;
                    }}
                    .cta-buttons {{
                        flex-direction: column;
                    }}
                    .footer {{
                        padding: 24px 20px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <div class="logo-container">
                        <img src="https://aegis.gdgoc.com/AEGIS.png" alt="Aegis Logo" class="logo" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                        <div style="display: none; font-size: 24px; font-weight: 700; color: #ffffff;">AEGIS</div>
                    </div>
                    <span class="success-icon">✅</span>
                    <h1 class="header-title">원본 사진 확인</h1>
                    <p class="header-subtitle">이미지 원본성이 검증되었습니다</p>
                </div>
                
                <div class="content">
                    <p class="user-greeting">안녕하세요, {username}님</p>
                    
                    <div class="success-section">
                        <h2 class="success-title">🎉 좋은 소식입니다!</h2>
                        <p class="success-message">
                            귀하의 이미지에서 원본 사진을 확인한 내역이 발생하였습니다.<br>
                            이미지가 원본 상태로 잘 보호되고 있습니다.
                        </p>
                    </div>
                    
                    <div class="confirmation-details">
                        <h3 class="details-title">확인 상세 정보</h3>
                        <table class="details-table">
                            <tr>
                                <td>
                                    <span class="detail-label">확인 시간</span>
                                    <span class="detail-value">{confirmation_time}</span>
                                </td>
                            </tr>
                            <tr>
                                <td>
                                    <span class="detail-label">이미지 파일명</span>
                                    <span class="detail-value">{image_name}</span>
                                </td>
                            </tr>
                            <tr>
                                <td>
                                    <span class="detail-label">원본 상태</span>
                                    <span class="detail-value status-confirmed">✅ 원본 확인됨</span>
                                </td>
                            </tr>
                            <tr>
                                <td>
                                    <span class="detail-label">검증 방법</span>
                                    <span class="detail-value">{verification_method}</span>
                                </td>
                            </tr>
                            {"<tr><td style='padding-top: 24px; text-align: center;'><span class='detail-label' style='display: block; margin-bottom: 16px;'>검증된 이미지</span><img src='" + image_url + "' alt='검증된 이미지' style='max-width: 300px; height: auto; border-radius: 8px; border: 2px solid #10b981; display: block; margin: 0 auto;'><p style='color: #6b7280; font-size: 12px; margin-top: 8px;'>※ 원본 확인된 이미지</p></td></tr>" if image_url else ""}
                        </table>
                    </div>
                    
                    <div class="confirmation-details">
                        <h3 class="details-title">보호된 원본 이미지 정보</h3>
                        <table class="details-table">
                            <tr>
                                <td>
                                    <span class="detail-label">이미지 ID</span>
                                    <span class="detail-value">{original_image_id}</span>
                                </td>
                            </tr>
                            <tr>
                                <td>
                                    <span class="detail-label">원본 파일명</span>
                                    <span class="detail-value">{original_filename}</span>
                                </td>
                            </tr>
                            <tr>
                                <td>
                                    <span class="detail-label">업로드 시간</span>
                                    <span class="detail-value">{upload_time}</span>
                                </td>
                            </tr>
                            <tr>
                                <td>
                                    <span class="detail-label">저작권 정보</span>
                                    <span class="detail-value">{copyright_info}</span>
                                </td>
                            </tr>
                        </table>
                        
                        <div style="margin-top: 24px; text-align: center;">
                            <h4 style="color: #1f2937; margin-bottom: 16px;">워터마크 이미지</h4>
                            <div style="justify-content: center; align-items: center;">
                                {"<div style='text-align: center;'><img src='" + watermark_image_url + "' alt='워터마크 이미지' style='max-width: 300px; height: auto; border-radius: 8px; border: 2px solid #10b981; display: block; margin: 0 auto;'><p style='color: #6b7280; font-size: 12px; margin-top: 8px;'>워터마크</p></div>" if watermark_image_url else ""}
                            </div>
                        </div>
                    </div>
                    
                    <div class="action-section">
                        <h3 class="action-title">상세 정보 확인</h3>
                        
                        <div class="cta-buttons">
                            <a href="{report_url}" class="btn-primary">
                                📊 상세 보고서 확인
                            </a>
                            <a href="mailto:kisiaaegis@gmail.com?subject=원본%20확인%20문의&body=안녕하세요.%20원본%20확인에%20관련하여%20문의드립니다." class="btn-secondary">
                                💬 지원팀 문의
                            </a>
                        </div>
                    </div>
                    
                    <div class="security-notice">
                        <p style="font-weight: 600; margin-bottom: 12px;">🛡️ 보안 알림</p>
                        <p>이 알림은 귀하의 이미지가 원본 상태로 확인되었음을 알려드리는 것입니다.</p>
                        <p>이미지 보안에 대한 추가 질문이 있으시면 언제든지 문의하세요.</p>
                    </div>
                    
                </div>
                
                <div class="footer">
                    <p class="footer-text">이 메일은 원본 확인 시 자동으로 발송된 메일입니다.</p>
                    <p class="footer-text">문의: kisiaaegis@gmail.com</p>
                    <p class="copyright">&copy; 2025 Aegis Security System. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return await self.send_email(user_email, subject, html_body, is_html=True)

    async def send_weekly_statistics_email(
        self, 
        user_email: str, 
        username: str,
        statistics: dict,
        period_start: str,
        period_end: str
    ) -> bool:
        """주간 위변조 통계 리포트 이메일 발송"""
        subject = f"📊 Aegis 주간 리포트 ({period_start} ~ {period_end})"
        
        # 통계 데이터 추출
        my_validations = statistics.get('my_validations_count', 0)
        my_image_validations = statistics.get('my_image_validations_count', 0)
        self_validations = statistics.get('self_validations_count', 0)
        total_validations = statistics.get('total_validations_count', 0)
        
        # 위변조 검출 건수
        forgery_detected = statistics.get('forgery_detected_count', 0)
        forgery_rate = statistics.get('forgery_detection_rate', 0.0)
        
        # 위변조 검출 레포트 목록
        forgery_reports = statistics.get('forgery_reports', [])
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: 'Malgun Gothic', Arial, sans-serif; margin: 0; padding: 20px; background-color: #f8fafc; }}
                .container {{ max-width: 800px; margin: 0 auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 28px; font-weight: 700; }}
                .header p {{ margin: 10px 0 0 0; font-size: 16px; opacity: 0.9; }}
                .content {{ padding: 40px; }}
                .stats-grid {{ 
                    display: flex; 
                    justify-content: space-between; 
                    gap: 40px; 
                    margin: 30px 0; 
                    flex-wrap: wrap;
                }}
                .stat-card {{ 
                    background: #f8fafc; 
                    border-radius: 10px; 
                    padding: 16px 10px; 
                    text-align: center; 
                    border-left: 4px solid #667eea; 
                    flex: 1; 
                    min-width: 120px;
                    max-width: 150px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                }}
                .stat-number {{ font-size: 32px; font-weight: 700; color: #667eea; margin-bottom: 8px; }}
                .stat-label {{ color: #64748b; font-size: 12px; font-weight: 500; line-height: 1.2; }}
                .highlight-section {{ background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border-radius: 8px; padding: 20px; margin: 20px 0; }}
                .highlight-title {{ font-size: 18px; font-weight: 600; color: #92400e; margin-bottom: 10px; }}
                .highlight-content {{ color: #b45309; }}
                .summary-section {{ background: #f1f5f9; border-radius: 8px; padding: 20px; margin: 20px 0; }}
                .footer {{ background: #f8fafc; padding: 20px; text-align: center; color: #64748b; font-size: 14px; }}
                .footer a {{ color: #667eea; text-decoration: none; }}
                .divider {{ height: 2px; background: linear-gradient(90deg, #667eea, #764ba2); margin: 25px 0; }}
                .btn-primary {{ 
                    display: inline-block !important; 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; 
                    background-color: #667eea !important;
                    color: #ffffff !important; 
                    padding: 15px 30px !important; 
                    text-decoration: none !important; 
                    border-radius: 8px !important; 
                    font-weight: 600 !important; 
                    font-size: 16px !important; 
                    margin: 20px 0 !important; 
                    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3) !important;
                    font-family: 'Malgun Gothic', Arial, sans-serif !important;
                    border: none !important;
                }}
                .btn-primary:visited {{ 
                    color: #ffffff !important;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
                }}
                .btn-primary:hover {{ 
                    color: #ffffff !important;
                    background: linear-gradient(135deg, #5a6fd8 0%, #6b4190 100%) !important;
                }}
                .button-container {{ text-align: center; margin: 30px 0; }}
                
                /* 모바일 대응 */
                @media (max-width: 600px) {{
                    .container {{ max-width: 100%; margin: 10px; }}
                    .content {{ padding: 20px; }}
                    .stats-grid {{ 
                        display: grid; 
                        grid-template-columns: 1fr 1fr; 
                        gap: 12px; 
                    }}
                    .stat-card {{ 
                        min-width: auto; 
                        padding: 20px 15px; 
                    }}
                    .stat-number {{ font-size: 28px; }}
                    .stat-label {{ font-size: 12px; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 주간 리포트</h1>
                    <p>{period_start} ~ {period_end}</p>
                    <p>안녕하세요, {username}님!</p>
                </div>
                
                <div class="content">
                    <h2 style="color: #1e293b; margin-bottom: 20px;">📈 이번 주 활동 요약</h2>
                    
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-number">{my_validations}</div>
                            <div class="stat-label">내가 검증한 이미지</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">{my_image_validations}</div>
                            <div class="stat-label">타인이 검증한 내 이미지</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">{self_validations}</div>
                            <div class="stat-label">내가 검증한 내 이미지</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">{total_validations}</div>
                            <div class="stat-label">전체 검증 건수</div>
                        </div>
                    </div>
                    
                    <div class="divider"></div>
                    
                    {self._generate_forgery_alerts_html(forgery_reports, forgery_detected, forgery_rate)}
                    
                    <div style="margin-top: 30px; padding: 20px; background: linear-gradient(135deg, #e0f2fe 0%, #b3e5fc 100%); border-radius: 8px;">
                        <p style="margin: 0; color: #0277bd; font-weight: 600;">💡 안전한 이미지 관리 팁</p>
                        <ul style="color: #01579b; margin-top: 10px; padding-left: 20px;">
                            <li>정기적으로 업로드한 이미지의 검증 현황을 확인하세요</li>
                            <li>위변조 의심 이미지 발견 시 즉시 제보해 주세요</li>
                            <li>중요한 이미지는 워터마크로 보호하세요</li>
                        </ul>
                    </div>
                    
                    <div class="button-container">
                        <a href="{self._build_frontend_url()}" class="btn-primary" 
                           style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); background-color: #667eea; color: #ffffff; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; margin: 20px 0; font-family: 'Malgun Gothic', Arial, sans-serif; border: none;">
                            🛡️ Aegis로 바로가기
                        </a>
                    </div>
                </div>
                
                <div class="footer">
                    <p>이 리포트는 매주 일요일 자동으로 발송됩니다.</p>
                    <p>사용자가 원할 때 수동으로 발송할 수도 있습니다.</p>
                    <p><a href="{self._build_frontend_url()}">Aegis</a>와 함께 안전한 이미지 관리를 하세요!</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return await self.send_email(user_email, subject, html_body, is_html=True)

    async def send_custom_period_statistics_email(
        self, 
        user_email: str, 
        username: str,
        statistics: dict,
        period_start: str,
        period_end: str
    ) -> bool:
        """지정 기간 위변조 통계 리포트 이메일 발송"""
        # 기간 일수 계산
        from datetime import datetime
        start_dt = datetime.strptime(period_start, '%Y-%m-%d').date()
        end_dt = datetime.strptime(period_end, '%Y-%m-%d').date()
        days_count = (end_dt - start_dt).days + 1
        
        subject = f"📊 Aegis {days_count}일간 리포트 ({period_start} ~ {period_end})"
        
        # 통계 데이터 추출
        my_validations = statistics.get('my_validations_count', 0)
        my_image_validations = statistics.get('my_image_validations_count', 0)
        self_validations = statistics.get('self_validations_count', 0)
        total_validations = statistics.get('total_validations_count', 0)
        
        # 위변조 검출 건수
        forgery_detected = statistics.get('forgery_detected_count', 0)
        forgery_rate = statistics.get('forgery_detection_rate', 0.0)
        
        # 위변조 검출 레포트 목록
        forgery_reports = statistics.get('forgery_reports', [])
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: 'Malgun Gothic', Arial, sans-serif; margin: 0; padding: 20px; background-color: #f8fafc; }}
                .container {{ max-width: 800px; margin: 0 auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 28px; font-weight: 700; }}
                .header p {{ margin: 10px 0 0 0; font-size: 16px; opacity: 0.9; }}
                .content {{ padding: 40px; }}
                .stats-grid {{ 
                    display: flex; 
                    justify-content: space-between; 
                    gap: 4px; 
                    margin: 30px 0; 
                    flex-wrap: wrap;
                }}
                .stat-card {{ 
                    background: #f8fafc; 
                    border-radius: 10px; 
                    padding: 16px 10px; 
                    text-align: center; 
                    border-left: 4px solid #667eea; 
                    flex: 1; 
                    min-width: 120px;
                    max-width: 150px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                }}
                .stat-number {{ font-size: 32px; font-weight: 700; color: #667eea; margin-bottom: 8px; }}
                .stat-label {{ color: #64748b; font-size: 12px; font-weight: 500; line-height: 1.2; }}
                .highlight-section {{ background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border-radius: 8px; padding: 20px; margin: 20px 0; }}
                .highlight-title {{ font-size: 18px; font-weight: 600; color: #92400e; margin-bottom: 10px; }}
                .highlight-content {{ color: #b45309; }}
                .summary-section {{ background: #f1f5f9; border-radius: 8px; padding: 20px; margin: 20px 0; }}
                .footer {{ background: #f8fafc; padding: 20px; text-align: center; color: #64748b; font-size: 14px; }}
                .footer a {{ color: #667eea; text-decoration: none; }}
                .divider {{ height: 2px; background: linear-gradient(90deg, #667eea, #764ba2); margin: 25px 0; }}
                .btn-primary {{ 
                    display: inline-block !important; 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; 
                    background-color: #667eea !important;
                    color: #ffffff !important; 
                    padding: 15px 30px !important; 
                    text-decoration: none !important; 
                    border-radius: 8px !important; 
                    font-weight: 600 !important; 
                    font-size: 16px !important; 
                    margin: 20px 0 !important; 
                    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3) !important;
                    font-family: 'Malgun Gothic', Arial, sans-serif !important;
                    border: none !important;
                }}
                .btn-primary:visited {{ 
                    color: #ffffff !important;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
                }}
                .btn-primary:hover {{ 
                    color: #ffffff !important;
                    background: linear-gradient(135deg, #5a6fd8 0%, #6b4190 100%) !important;
                }}
                .button-container {{ text-align: center; margin: 30px 0; }}
                
                /* 모바일 대응 */
                @media (max-width: 600px) {{
                    .container {{ max-width: 100%; margin: 10px; }}
                    .content {{ padding: 20px; }}
                    .stats-grid {{ 
                        display: grid; 
                        grid-template-columns: 1fr 1fr; 
                        gap: 12px; 
                    }}
                    .stat-card {{ 
                        min-width: auto; 
                        padding: 20px 15px; 
                    }}
                    .stat-number {{ font-size: 28px; }}
                    .stat-label {{ font-size: 12px; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 {days_count}일간 리포트</h1>
                    <p>{period_start} ~ {period_end}</p>
                    <p>안녕하세요, {username}님!</p>
                </div>
                
                <div class="content">
                    <h2 style="color: #1e293b; margin-bottom: 20px;">📈 선택 기간 활동 요약</h2>
                    
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-number">{my_validations}</div>
                            <div class="stat-label">내가 검증한 이미지</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">{my_image_validations}</div>
                            <div class="stat-label">타인이 검증한 내 이미지</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">{self_validations}</div>
                            <div class="stat-label">내가 검증한 내 이미지</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">{total_validations}</div>
                            <div class="stat-label">전체 검증 건수</div>
                        </div>
                    </div>
                    
                    <div class="divider"></div>
                    
                    {self._generate_forgery_alerts_html(forgery_reports, forgery_detected, forgery_rate)}
                    
                    <div style="margin-top: 30px; padding: 20px; background: linear-gradient(135deg, #e0f2fe 0%, #b3e5fc 100%); border-radius: 8px;">
                        <p style="margin: 0; color: #0277bd; font-weight: 600;">💡 안전한 이미지 관리 팁</p>
                        <ul style="color: #01579b; margin-top: 10px; padding-left: 20px;">
                            <li>정기적으로 업로드한 이미지의 검증 현황을 확인하세요</li>
                            <li>위변조 의심 이미지 발견 시 즉시 제보해 주세요</li>
                            <li>중요한 이미지는 워터마크로 보호하세요</li>
                        </ul>
                    </div>
                    
                    <div class="button-container">
                        <a href="{self._build_frontend_url()}" class="btn-primary" 
                           style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); background-color: #667eea; color: #ffffff; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; margin: 20px 0; font-family: 'Malgun Gothic', Arial, sans-serif; border: none;">
                            🛡️ Aegis로 바로가기
                        </a>
                    </div>
                </div>
                
                <div class="footer">
                    <p>이 리포트는 사용자가 요청한 맞춤 기간 리포트입니다.</p>
                    <p><a href="{self._build_frontend_url()}">Aegis</a>와 함께 안전한 이미지 관리를 하세요!</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return await self.send_email(user_email, subject, html_body, is_html=True)

    def _generate_forgery_alerts_html(self, forgery_reports: list, forgery_detected: int, forgery_rate: float = 0.0) -> str:
        """위변조 검출 알림 HTML 생성"""
        if forgery_detected == 0:
            return ""
        
        # 레포트 링크 목록 생성
        report_links_html = ""
        if forgery_reports:
            report_links_html = "<div style='margin-top: 15px;'>"
            report_links_html += "<p style='margin: 0 0 10px 0; color: #b45309; font-weight: 600;'>📋 검출된 위변조 레포트:</p>"
            report_links_html += "<ul style='margin: 0; padding-left: 20px; color: #b45309;'>"
            
            for report in forgery_reports:
                report_url = self._build_frontend_url(f"result/{report['validation_uuid']}")
                report_links_html += f"""
                    <li style='margin: 8px 0; line-height: 1.4;'>
                        <a href='{report_url}' style='color: #dc2626; text-decoration: none; font-weight: 600;'>
                            {report['filename']}
                        </a>
                        <span style='color: #b45309; font-size: 13px;'>
                            (변조율: {report['modification_rate']:.1f}%, {report['validation_time']}) - 
                            <a href='{report_url}' style='color: #dc2626; text-decoration: underline; font-size: 12px;'>
                                상세보기
                            </a>
                        </span>
                    </li>
                """
            
            report_links_html += "</ul>"
            if len(forgery_reports) == 5 and forgery_detected > 5:
                report_links_html += f"<p style='margin: 10px 0 0 0; color: #b45309; font-size: 12px; font-style: italic;'>* 총 {forgery_detected}건 중 최근 5건만 표시</p>"
            report_links_html += "</div>"
        
        return f"""
        <div class='highlight-section'>
            <div class='highlight-title'>🚨 위변조 검출 알림</div>
            <div class='highlight-content'>
                이번 주 총 <strong>{forgery_detected}건</strong>의 위변조가 검출되었습니다.
                {report_links_html}
            </div>
        </div>
        """


email_service = EmailService()
