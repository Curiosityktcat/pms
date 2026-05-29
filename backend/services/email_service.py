import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.header import Header
from models import db
from models.sys_config import SysConfig


def get_email_config():
    """从数据库读取邮件配置"""
    keys = [
        "email_smtp_host",
        "email_smtp_port",
        "email_address",
        "email_auth_code",
        "email_sender_name",
    ]
    result = {}
    for k in keys:
        row = db.session.get(SysConfig, k)
        result[k] = row.value if row else ""
    return result


def send_email(
    to_addr: str,
    subject: str,
    body_html: str,
    attachment_bytes=None,
    attachment_filename=None,
    extra_attachments=None,   # list of (bytes_or_io, filename)
):
    """
    通过 163 SMTP 发送邮件。
    attachment_bytes: bytes 或 BytesIO
    attachment_filename: 附件文件名（含扩展名）
    """
    cfg = get_email_config()
    if not cfg.get("email_address") or not cfg.get("email_auth_code"):
        raise ValueError("邮件配置未完成，请先在系统设置中配置发件邮箱")

    sender_name = cfg.get("email_sender_name") or "内江市第一人民医院采购部"
    from_addr = cfg["email_address"]

    msg = MIMEMultipart()
    msg["From"] = f"{Header(sender_name, 'utf-8').encode()} <{from_addr}>"
    msg["To"] = to_addr
    msg["Subject"] = Header(f"【{sender_name}】{subject}", "utf-8")

    msg.attach(MIMEText(body_html, "html", "utf-8"))

    def _attach_file(data, fname):
        if hasattr(data, "read"):
            data = data.read()
        part = MIMEApplication(data, Name=fname)
        from email.header import Header as _Header
        encoded_name = _Header(fname, "utf-8").encode()
        part["Content-Disposition"] = f'attachment; filename="{encoded_name}"'
        msg.attach(part)

    if attachment_bytes and attachment_filename:
        _attach_file(attachment_bytes, attachment_filename)

    # 额外附件列表 [(bytes_or_io, filename), ...]
    for att_bytes, att_name in (extra_attachments or []):
        _attach_file(att_bytes, att_name)

    smtp_host = cfg.get("email_smtp_host") or "smtp.163.com"
    smtp_port = int(cfg.get("email_smtp_port") or 465)

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx) as smtp:
        smtp.login(from_addr, cfg["email_auth_code"])
        smtp.sendmail(from_addr, [to_addr], msg.as_bytes())
