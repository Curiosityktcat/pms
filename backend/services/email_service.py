import imaplib
import smtplib
import ssl
import email as _email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.header import Header, decode_header
from models import db
from models.sys_config import SysConfig

# 163 的 IMAP 防垃圾要求登录后发 ID 命令，否则报 Unsafe Login；先注册该命令
imaplib.Commands.setdefault("ID", ("AUTH", "SELECTED"))


def _decode_hdr(s):
    if not s:
        return ""
    return "".join(
        t.decode(enc or "utf-8", "ignore") if isinstance(t, bytes) else t
        for t, enc in decode_header(s))


def _imap_host(cfg):
    """由 smtp 主机推断 imap 主机（smtp.163.com → imap.163.com）。"""
    host = cfg.get("email_smtp_host") or "smtp.163.com"
    return host.replace("smtp.", "imap.", 1)


def _imap_connect(cfg):
    """登录 IMAP 并选中收件箱（163 反垃圾要求登录后报客户端 ID）。"""
    addr = cfg.get("email_address")
    code = cfg.get("email_auth_code")
    if not addr or not code:
        raise RuntimeError("邮箱未配置，无法收信")
    M = imaplib.IMAP4_SSL(_imap_host(cfg), 993)
    M.login(addr, code)
    try:
        M._simple_command("ID", '("name" "pms" "version" "1.0")')
        M._untagged_response("OK", [], "ID")
    except Exception:
        pass
    M.select("INBOX")
    return M


def fetch_inbox(limit=200):
    """连邮箱拉取收件箱最近若干封邮件，返回
    [{uid, subject, from_name, from_addr, date}]。uid 为 IMAP UID（稳定，
    可供 fetch_attachments_by_uid 二次下载附件）。须在 app 上下文内调用。"""
    M = _imap_connect(get_email_config())
    try:
        typ, data = M.uid("search", None, "ALL")
        ids = data[0].split()
        out = []
        for i in reversed(ids[-limit:]):
            typ, d = M.uid("fetch", i, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
            if not d or not d[0]:
                continue
            msg = _email.message_from_bytes(d[0][1])
            frm = _decode_hdr(msg.get("From"))
            addr_m = ""
            if "<" in frm and ">" in frm:
                addr_m = frm[frm.find("<") + 1:frm.find(">")]
            out.append({
                "uid": i.decode() if isinstance(i, bytes) else str(i),
                "subject": _decode_hdr(msg.get("Subject")),
                "from_name": frm.split("<")[0].strip().strip('"'),
                "from_addr": addr_m or frm,
                "date": msg.get("Date", ""),
            })
        return out
    finally:
        try:
            M.logout()
        except Exception:
            pass


def fetch_attachments_by_uid(uids):
    """按 UID 下载整封邮件并抽取附件，返回 {uid: [(文件名, bytes), ...]}。
    只取带文件名的附件部分（跳过正文/内嵌图标等无名部分）。"""
    if not uids:
        return {}
    M = _imap_connect(get_email_config())
    out = {}
    try:
        for uid in uids:
            typ, d = M.uid("fetch", uid, "(BODY.PEEK[])")
            if typ != "OK" or not d or not d[0]:
                out[uid] = []
                continue
            msg = _email.message_from_bytes(d[0][1])
            files = []
            for part in msg.walk():
                fname = part.get_filename()
                if not fname:
                    continue
                payload = part.get_payload(decode=True)
                if payload:
                    files.append((_decode_hdr(fname), payload))
            out[uid] = files
        return out
    finally:
        try:
            M.logout()
        except Exception:
            pass


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
