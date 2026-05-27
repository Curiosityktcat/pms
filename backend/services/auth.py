import hashlib
import secrets
from models import db
from models.user import User


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200000).hex()


def check_login(username, password):
    """验证用户名密码，成功返回 User 对象，失败返回 None。"""
    user = db.session.execute(
        db.select(User).filter_by(username=username, active=1)
    ).scalar_one_or_none()
    if user and hash_pw(password, user.salt) == user.pw_hash:
        return user
    return None


def change_password(username, old_pw, new_pw):
    """修改密码，返回 (ok: bool, message: str)。"""
    user = db.session.execute(
        db.select(User).filter_by(username=username)
    ).scalar_one_or_none()
    if not user:
        return False, "用户不存在"
    if hash_pw(old_pw, user.salt) != user.pw_hash:
        return False, "原密码错误"
    salt = secrets.token_hex(16)
    user.salt = salt
    user.pw_hash = hash_pw(new_pw, salt)
    db.session.commit()
    return True, "密码已修改"
