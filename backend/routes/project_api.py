from flask import Blueprint, request, session, jsonify
from models import db
from models.project import Project
from models.agency import Agency
from services import project as svc
from services.numbering import M_YIJIA, M_XUNJIA, M_JINGXUAN, M_SOLE, M_JINGJI
from services.project_progress import build_progress
from routes.utils import login_required

bp = Blueprint("project", __name__, url_prefix="/api/projects")

STATUSES = ["立项", "委托代理", "编制中", "审核中", "已发公告", "报名中", "开标", "已定标", "合同签订", "已归档"]


@bp.route("/meta", methods=["GET"])
@login_required
def meta():
    """前端立项表单需要的静态数据：代理机构列表、采购方式、状态列表。"""
    agencies = db.session.execute(db.select(Agency).filter_by(active=1)).scalars().all()
    return jsonify({
        "ok": True,
        "agencies": [a.to_dict() for a in agencies],
        "methods": [M_YIJIA, M_XUNJIA, M_JINGXUAN, M_SOLE, M_JINGJI],
        "statuses": STATUSES,
    })


@bp.route("", methods=["GET"])
@login_required
def list_projects():
    show_deleted = request.args.get("deleted") == "1"
    rows = svc.list_projects(
        role=session["role"],
        agency_code=session.get("agency_code", ""),
        officer=session.get("display_name", ""),
        show_deleted=show_deleted,
        dept_code=session.get("dept_code", ""),
    )
    _attach_round_info(rows)
    return jsonify({"ok": True, "data": rows, "total": len(rows)})


@bp.route("/bid-open", methods=["GET"])
@login_required
def bid_open_projects():
    """授权函专用：处于「开标期」的代理项目。

    开标期 = 已发公告 ~ 采购结果确认前，跨两个阶段：
      · bid_open：公告已确认、可开标尚未确认（即将开标）
      · result  ：可开标已确认、采购结果未确认（已判定可开标、待结果）
    业务流程是「先确认可开标 → 再生成授权函 + 传开标记录」，所以 result 段也必须可见
    （流标 round_failed 已自动开下一轮，不在此列）。

    授权函是采购部部门事务，不按经办人隔离——采购部各角色(officer/assistant/leader/admin)
    都能看并据此生成授权函；代理机构仅本机构。
    """
    role = session.get("role", "")
    if role == "agency":
        rows = svc.list_projects(role="agency", agency_code=session.get("agency_code", ""))
    else:
        rows = svc.list_projects(role="__all__")  # 采购部：全部可见
    _attach_round_info(rows)
    out = [r for r in rows
           if r.get("current_stage") in ("bid_open", "result")
           and r.get("agency_code") and not r.get("is_draft")]
    return jsonify({"ok": True, "data": out, "total": len(out)})


@bp.route("/<int:pid>/progress", methods=["GET"])
@login_required
def project_progress(pid):
    """项目进展图：逐轮逐节点的状态/时间/操作人（见 services.project_progress）。"""
    project = db.session.get(Project, pid)
    if not project:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if session.get("role") == "agency" and project.agency_code != session.get("agency_code", ""):
        return jsonify({"ok": False, "error": "无权查看"}), 403
    return jsonify({"ok": True, "data": build_progress(project)})


def _attach_round_info(rows):
    """给项目行补充 package_count、current_round、current_stage、pending_contract、pending。

    pending = 当前处理人（此刻卡在谁手上、哪个环节、等了几天），见 services/pending_owner.py。
    """
    if not rows:
        return
    from models.package import Package
    from services.project_progress import stage_map
    ids = [r["id"] for r in rows]
    pkg_counts = dict(db.session.execute(
        db.select(Package.project_id, db.func.count())
        .where(Package.project_id.in_(ids))
        .group_by(Package.project_id)
    ).all())
    stages = stage_map(ids)
    # 已成功推送 rd-web 合同审签的项目（任一份合同有流水号即算）
    from models.contract import Contract as _Contract
    contract_rdweb_ids = {row[0] for row in db.session.execute(
        db.select(_Contract.project_id)
        .where(_Contract.project_id.in_(ids))
        .where(_Contract.rdweb_serial_no != "")
    ).all()}
    for r in rows:
        st = stages.get(r["id"], {})
        r["package_count"] = pkg_counts.get(r["id"], 0)
        r["current_round"] = st.get("current_round", 0)
        r["current_stage"] = st.get("current_stage", "")
        r["pending_contract"] = st.get("pending_contract", 0)
        r["contract_rdweb_submitted"] = r["id"] in contract_rdweb_ids
        r["agency_rdweb_submitted"] = bool(r.get("agency_rdweb_serial_no"))

    from services.pending_owner import attach_pending
    attach_pending(rows, "id")


def _auto_push_agency_agreement(p):
    """立项完成且选定了代理公司 → 自动签代理协议并推 rd-web 合同审签单。

    手绘《rd-web 自动化改进计划》①。推送本身是后台线程，这里只负责发起；
    **任何失败都不能影响立项**，页面上还能到「委托代理协议」手动推。
    """
    try:
        if p.is_draft or not p.agency_code or (p.agency_rdweb_serial_no or ""):
            return {}
        from routes.rdweb_approval_api import auto_push_enabled
        if not auto_push_enabled():
            return {"auto": False, "reason": "自动推送已关闭"}
        from routes.agency_agreement_api import submit_agency_agreement_to_rdweb
        submit_agency_agreement_to_rdweb(p.id)
        return {"auto": True, "ok": True, "kind": "agency_agreement",
                "msg": "已开始自动推送委托代理协议到 rd-web 合同审签"}
    except Exception as e:      # noqa: BLE001
        return {"auto": True, "ok": False, "kind": "agency_agreement",
                "msg": f"自动推送未启动：{e}"[:200]}


@bp.route("", methods=["POST"])
@login_required
def create_project():
    if session["role"] != "officer":
        return jsonify({"ok": False, "error": "仅项目经办人可立项"}), 403
    data = request.get_json(force=True) or {}
    push_info = {}
    demand_id   = data.pop("demand_id",   None)  # 从采购需求立项时传入
    demand_type = data.pop("demand_type", None)  # 'gov' / 'competition' / 'sole_source' 等
    distribution_id = data.pop("distribution_id", None)  # 从「项目分发」立项时传入
    try:
        p, number = svc.create_project(data, session["user"], session["display_name"])
        if p.is_draft:
            msg = "已存为草稿（未生成编号）"
        else:
            use_agency = bool(p.agency_code)
            msg = f"立项成功，编号 {number}（{'走代理' if use_agency else '不走代理'}，线{p.line}）"
            # 政府采购项目立项后直接归档
            if demand_type == "gov":
                p.status = "已归档"
                db.session.commit()
                msg += "（政府采购，已自动归档）"
            # 如果是从采购需求立项，标记需求为已立项
            if demand_id:
                try:
                    from models.procurement_demand import ProcurementDemand
                    demand = db.session.get(ProcurementDemand, int(demand_id))
                    if demand:
                        demand.project_id = p.id
                        demand.status = "已立项"
                        import datetime as _dt
                        demand.updated_at = _dt.datetime.now().isoformat(timespec="seconds")
                        db.session.commit()
                except Exception:
                    pass  # 非致命错误，不影响立项本身
            # 从「项目分发」立项：回填关联项目并标记已立项
            if distribution_id:
                try:
                    from models.project_distribution import ProjectDistribution
                    dist = db.session.get(ProjectDistribution, int(distribution_id))
                    if dist:
                        dist.project_id = p.id
                        dist.status = "已立项"
                        import datetime as _dt2
                        dist.updated_at = _dt2.datetime.now().isoformat(timespec="seconds")
                        db.session.commit()
                        # 注意：分发附件不再自动复制成 5.1 采购需求附件。
                        # 项目池里混有医院内部文件，全量带入会连同内部文件一起打包给代理机构；
                        # 改由经办人在「5.1 采购需求确认」按需从项目池挑选（见
                        # procurement_doc_api 的 pool-attachments / pool-attachments/import）。
                except Exception:
                    pass
            # 立项完成、代理公司已定 → 自动签代理协议推 rd-web 审签
            push_info = _auto_push_agency_agreement(p)
        return jsonify({"ok": True, "message": msg, "data": p.to_dict(),
                        "rdweb_push": push_info}), 201
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.route("/<int:pid>", methods=["GET"])
@login_required
def get_project(pid):
    try:
        p = svc.get_project(
            pid,
            role=session["role"],
            agency_code_session=session.get("agency_code", ""),
            officer_session=session.get("display_name", ""),
        )
    except (ValueError, PermissionError) as e:
        code = 404 if isinstance(e, ValueError) else 403
        return jsonify({"ok": False, "error": str(e)}), code
    d = p.to_dict()
    d["agency_name"] = svc.get_agency_name(p.agency_code)
    agencies = db.session.execute(db.select(Agency).filter_by(active=1)).scalars().all()
    return jsonify({
        "ok": True,
        "data": d,
        "agencies": [a.to_dict() for a in agencies],
        "methods": [M_YIJIA, M_XUNJIA, M_JINGXUAN, M_SOLE, M_JINGJI],
        "statuses": STATUSES,
    })


@bp.route("/<int:pid>", methods=["PUT"])
@login_required
def update_project(pid):
    data = request.get_json(force=True) or {}
    try:
        p, number = svc.update_project(
            pid, data,
            role=session["role"],
            agency_code_session=session.get("agency_code", ""),
            officer_session=session.get("display_name", ""),
        )
        msg = f"草稿已立项，编号 {number}" if number else "已保存"
        return jsonify({"ok": True, "message": msg, "data": p.to_dict()})
    except PermissionError as e:
        return jsonify({"ok": False, "error": str(e)}), 403
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.route("/<int:pid>", methods=["DELETE"])
@login_required
def delete_project(pid):
    try:
        svc.delete_project(
            pid,
            role=session["role"],
            agency_code_session=session.get("agency_code", ""),
            officer_session=session.get("display_name", ""),
        )
        return jsonify({"ok": True, "message": "已删除（可在「已删除」标签中恢复）"})
    except PermissionError as e:
        return jsonify({"ok": False, "error": str(e)}), 403
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404


@bp.route("/<int:pid>/restore", methods=["POST"])
@login_required
def restore_project(pid):
    try:
        svc.restore_project(
            pid,
            role=session["role"],
            agency_code_session=session.get("agency_code", ""),
            officer_session=session.get("display_name", ""),
        )
        return jsonify({"ok": True, "message": "项目已恢复"})
    except PermissionError as e:
        return jsonify({"ok": False, "error": str(e)}), 403
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
