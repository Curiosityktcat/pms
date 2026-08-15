"""把存量 dept 账号幂等迁移为归口管理科室或需求科室角色。

只改角色，不碰密码、科室码和其它账号字段，因此登录凭据与可见范围保持不变。
"""
from app import create_app
from models import db
from models.dept import Dept
from models.user import User


def migrate():
    rows = db.session.execute(db.select(User).filter_by(role="dept")).scalars().all()
    changed = 0
    skipped = []
    for user in rows:
        dept = db.session.execute(db.select(Dept).filter_by(code=user.dept_code)).scalar_one_or_none()
        if not dept:
            # 科室归属不明时不能猜角色；保留旧角色可确保仍按科室账号收口。
            skipped.append(user.username)
            continue
        user.role = "dept_manage" if dept.dept_type == "行后" and dept.code != "CGB" else "dept_demand"
        changed += 1
    db.session.commit()
    return changed, skipped


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        count, skipped_users = migrate()
        print(f"迁移完成：更新 {count} 个账号，跳过 {len(skipped_users)} 个账号")
        if skipped_users:
            print("未找到科室字典：" + "、".join(skipped_users))
