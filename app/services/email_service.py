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
                        <a href="https://aegis.gdgoc.com" class="cta-button">
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
        subject = f"🚨 [긴급] 이미지 #{original_image_info.get('image_id', 'N/A')} 위변조 검출 알림"
        
        detection_time = detection_info.get('detection_time', 'N/A')
        image_name = detection_info.get('image_name', 'N/A')
        confidence_score = detection_info.get('confidence_score', 'N/A')
        detection_method = detection_info.get('detection_method', 'AI 분석')
        
        # 원본 이미지 정보
        original_info = original_image_info or {}
        original_image_id = original_info.get('image_id', 'N/A')
        original_filename = original_info.get('filename', 'N/A')
        upload_time = original_info.get('upload_time', 'N/A')
        copyright_info = original_info.get('copyright_info', '저작권자 정보 없음')
        watermark_image_url = original_info.get('watermark_image_url', '')
        
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
                .details-grid {{
                    display: table;
                    width: 100%;
                    border-spacing: 0;
                }}
                .detail-item {{
                    display: table-row;
                    padding: 12px 0;
                    border-bottom: 1px solid #222222;
                }}
                .detail-item:last-child {{
                    border-bottom: none;
                }}
                .detail-label {{
                    display: table-cell;
                    font-size: 15px;
                    color: #888888;
                    font-weight: 500;
                    padding: 12px 30px 12px 0;
                    width: 160px;
                    min-width: 160px;
                    vertical-align: top;
                    white-space: nowrap;
                }}
                .detail-value {{
                    display: table-cell;
                    font-size: 15px;
                    color: #ffffff;
                    font-weight: 600;
                    line-height: 1.4;
                    word-break: break-word;
                    padding: 12px 0;
                    vertical-align: top;
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
                        <div class="details-grid">
                            <div class="detail-item">
                                <span class="detail-label">검출 시간</span>
                                <span class="detail-value">{detection_time}</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">이미지 파일명</span>
                                <span class="detail-value">{image_name}</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">위변조 신뢰도</span>
                                <span class="detail-value">
                                    {"RobustWide는 변조률을 제공하지 않음" if detection_method == "RobustWide" else f"{confidence_score}%"}
                                </span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">검출 방법</span>
                                <span class="detail-value">{detection_method}</span>
                            </div>
                        </div>
                    </div>
                    
                    {"<div class='image-preview'><h4 style='color: #ffffff; margin-bottom: 16px;'>검출된 위변조 이미지</h4><img src='" + image_url + "' alt='검출된 위변조 이미지' style='max-width: 300px; height: auto; border-radius: 8px; border: 2px solid #dc2626; display: block; margin: 0 auto;'><p class='image-caption'>※ 위변조가 의심되는 이미지</p></div>" if image_url else ""}
                    
                    <div class="detection-details">
                        <h3 class="details-title">보호된 원본 이미지 정보</h3>
                        <div class="details-grid">
                            <div class="detail-item">
                                <span class="detail-label">이미지 ID</span>
                                <span class="detail-value">{original_image_id}</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">원본 파일명</span>
                                <span class="detail-value">{original_filename}</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">업로드 시간</span>
                                <span class="detail-value">{upload_time}</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">저작권 정보</span>
                                <span class="detail-value">{copyright_info}</span>
                            </div>
                        </div>
                        
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
                            <a href="mailto:kisiaaegis@gmail.com" class="btn-secondary">
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


email_service = EmailService()