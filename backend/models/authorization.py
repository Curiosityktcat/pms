"""人员授权记录。"""
from datetime import datetime

from . import db


class Authorization(db.Model):
    __tablename__ = "authorizations"

    id = db.Column(db.Integer, primary_key=True)
    grantee_username = db.Column(db.String(100), nullable=False, index=True)
    grantee_name = db.Column(db.String(50), nullable=False, default="")
    grantee_dept_code = db.Column(db.String(20), nullable=False, default="", index=True)
    source = db.Column(db.String(20), nullable=False)
    granter_name = db.Column(db.String(50), nullable=False, default="")
    granter_dept_code = db.Column(db.String(20), nullable=False, default="", index=True)
    # 委托是否继续有效必须和授权当时的负责人比，不能只保存当前负责人姓名。
    granter_head_snapshot = db.Column(db.String(50), nullable=False, default="")
    doc_no = db.Column(db.String(100), nullable=False, default="")
    perm_keys = db.Column(db.Text, nullable=False, default="[]")
    valid_from = db.Column(db.String(10), nullable=False)
    valid_to = db.Column(db.String(10), nullable=False)
    doc_path = db.Column(db.Text, nullable=False)
    doc_name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    created_by = db.Column(db.String(100), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    revoked_by = db.Column(db.String(100), nullable=False, default="")
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoke_reason = db.Column(db.Text, nullable=False, default="")

