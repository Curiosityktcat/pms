"""按《2026-8-15 人员和权限设计》的科室名单清理重复科室。

用户 2026-08-16：「用户里面有一些重复的项，比如院办是行政办公室的简称，
**只按照我给的那个文件出科室**」。

处理原则：**停用不删除**。科室名是历史项目里 manage_dept/demand_dept 的匹配依据，
删掉会让老项目找不到归属；停用后不再出现在建号/选择列表里，历史匹配仍可用别名兜住。

  院办(YB)      → 「院办」并入 行政办公室(XZB) 的别名，YB 停用
  预保科(YBK)   → 名单里没有，停用（疑似并入公共卫生科，无实据不合并别名）
  资产管理组(ZCGLZ) → 名单里没有（来自内控的采购职能科室），停用

同时停用这些科室对应的**账号**，否则用户管理里仍是重复项。
"""
import sys

sys.path.insert(0, ".")

from app import create_app
from models import db
from models.dept import Dept
from models.user import User

MERGE = {"YB": ("XZB", "院办")}          # 被并科室码 → (目标科室码, 要加的别名)
RETIRE = {
    "YB":    "2026-08-16 用户确认：院办是行政办公室的简称，已并入行政办公室(XZB)",
    "YBK":   "2026-08-16 不在全院科室名单中，停用；疑似并入公共卫生科，无实据故不合并别名",
    "ZCGLZ": "2026-08-16 不在全院科室名单中（来自采购管理内控的采购职能科室），停用",
}
DEPT_ROLES = ("dept", "dept_manage", "dept_demand")


def main():
    app = create_app()
    with app.app_context():
        print("库:", app.config["SQLALCHEMY_DATABASE_URI"].split("/")[-1])
        for src, (dst, alias) in MERGE.items():
            target = db.session.execute(db.select(Dept).filter_by(code=dst)).scalar_one_or_none()
            if target is None:
                print(f"  跳过合并 {src}→{dst}：目标科室不存在")
                continue
            names = [a.strip() for a in (target.aliases or "").replace("、", ",").split(",") if a.strip()]
            if alias not in names:
                names.append(alias)
                target.aliases = ",".join(names)
                print(f"  {target.name} 别名 += {alias}")
        for code, note in RETIRE.items():
            d = db.session.execute(db.select(Dept).filter_by(code=code)).scalar_one_or_none()
            if d is None:
                continue
            if d.active:
                d.active = 0
                print(f"  停用科室 {d.name}({code})")
            if note not in (d.note or ""):
                d.note = ((d.note or "") + " " + note).strip()
            accs = db.session.execute(db.select(User).filter_by(dept_code=code).where(
                User.role.in_(DEPT_ROLES))).scalars().all()
            for a in accs:
                if a.active:
                    a.active = 0
                    print(f"    停用账号 {a.username}")
        db.session.commit()

        left = db.session.execute(db.select(Dept).filter_by(active=1)).scalars().all()
        hh = sum(1 for d in left if (d.dept_type or "") == "行后")
        lc = sum(1 for d in left if (d.dept_type or "") == "临床医技")
        print(f"启用科室 {len(left)} 个（行后 {hh}、临床医技 {lc}、未分类 {len(left)-hh-lc}）")
        na = db.session.execute(db.select(db.func.count()).select_from(User).where(
            User.role.in_(DEPT_ROLES), User.active == 1)).scalar_one()
        print("启用的科室账号:", na)
        unclassified = [d.name for d in left if not (d.dept_type or "")]
        print("仍未分类的科室:", "、".join(unclassified) or "无")


if __name__ == "__main__":
    main()
