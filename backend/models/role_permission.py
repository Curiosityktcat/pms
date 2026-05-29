from . import db


class RolePermission(db.Model):
    """角色 → 菜单权限映射，每行一个 (role, perm_key)。

    admin 角色不入表，运行时直接拥有全部权限。
    """

    __tablename__ = "role_permissions"

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False, index=True)
    perm_key = db.Column(db.String(50), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("role", "perm_key", name="uq_role_perm"),
    )
