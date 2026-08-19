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
    if new_pw == old_pw:
        return False, "新密码不能和原密码相同"
    if len(new_pw) < 8:
        return False, "新密码至少 8 位"
    salt = secrets.token_hex(16)
    user.salt = salt
    user.pw_hash = hash_pw(new_pw, salt)
    # 改完就不再是「一次性密码」了，闸门随之放开
    if hasattr(user, "must_change_pw"):
        user.must_change_pw = 0
    db.session.commit()
    return True, "密码已修改"
