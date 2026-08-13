"""代理机构考核的触发判据：所有中标包的合同都上传完了才算可考核。

原来按项目状态（已定标/合同签订/已归档）判断，太早——定标了但合同还没签、
盖章件还没上传，代理机构的活其实没干完，这时候打分不公平也打不准
（归档时效那一项根本还没有数据）。

改成看包：项目里每一个「已中标」的包，都要有一份状态为「合同上传」的合同，
才算这个项目的代理服务全部交付完毕，可以开始考核。
"""
from models import db
from models.package import Package
from models.contract import Contract


def ready_project_ids(project_ids):
    """从给定项目里筛出「所有中标包合同均已上传」的那些，返回 set。

    一次性把包和合同全捞出来在内存里算，避免逐项目 N+1 查询。
    """
    ids = [int(i) for i in project_ids]
    if not ids:
        return set()

    # 每个项目的已中标包号
    won = {}
    for pk in db.session.execute(
        db.select(Package).where(Package.project_id.in_(ids))
    ).scalars().all():
        if pk.status == "已中标":
            won.setdefault(pk.project_id, set()).add(str(pk.package_no))

    # 每个项目已完成上传（状态=合同上传）的合同包号
    uploaded = {}
    for c in db.session.execute(
        db.select(Contract).where(Contract.project_id.in_(ids))
    ).scalars().all():
        if c.status == "合同上传":
            uploaded.setdefault(c.project_id, set()).add(str(c.package_no or "1"))

    out = set()
    for pid in ids:
        w = won.get(pid) or set()
        if not w:
            continue          # 没有中标包（全废标/尚未定标）→ 谈不上考核
        if w <= (uploaded.get(pid) or set()):
            out.add(pid)
    return out


def readiness(project_id):
    """单个项目的可考核情况，给前端解释「为什么还不能考核」。"""
    pid = int(project_id)
    won, uploaded = [], []
    for pk in db.session.execute(
        db.select(Package).filter_by(project_id=pid)
    ).scalars().all():
        if pk.status == "已中标":
            won.append(str(pk.package_no))
    for c in db.session.execute(
        db.select(Contract).filter_by(project_id=pid)
    ).scalars().all():
        if c.status == "合同上传":
            uploaded.append(str(c.package_no or "1"))
    missing = sorted(set(won) - set(uploaded), key=lambda x: (len(x), x))
    return {
        "won_packages": sorted(set(won), key=lambda x: (len(x), x)),
        "uploaded_packages": sorted(set(uploaded), key=lambda x: (len(x), x)),
        "missing_packages": missing,
        "ready": bool(won) and not missing,
        "reason": ("尚无中标包" if not won
                   else (f"包 {'、'.join(missing)} 的合同还没上传" if missing else "")),
    }
