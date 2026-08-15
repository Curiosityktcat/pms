"""项目要件 → rd-web「采购项目审批流程」自动推送（走审批即盖章）。

手绘《rd-web 自动化改进计划》里 ②③④ 三个环节：经办人在 PMS 里确认完
某个要件，就把该要件推到 rd-web 的采购项目审批流程去盖章，不用再手工填一遍。

    kind          PMS 触发点                要件（archive_print 生成）  rd-web 下拉「项目资料名称」
    doc_confirm   5.2 采购文件确认后        采购文件确认函              采购文件确认（非政采）
    auth_letter   授权函生成后              授权函                      采购人代表授权
    result        9. 采购结果确认后         采购结果确认函              采购结果确认函

下拉选项是「含此文字即可」的模糊匹配（见 procurement_approval_submit
._select_material_type）。下面这三个字串是 2026-08-14 登录 rd-web 实测的真实选项
（当天全部选项：进口产品审批／单一来源论证／变更采购方式的申请／项目自查清单／
采购人代表授权／采购文件确认（非政采）／代理协议签订／采购结果确认函／备案资料盖章）——
注意是「采购人**代表**授权」「非**政**采」，跟手写计划里的措辞不一样。
万一 rd-web 改了措辞，报错会把真实可选项原样带出来，照着改这里即可。
"""
import json
import os
import tempfile
import threading
import time

# 一次推送最长按 8 分钟算，与 rdweb_contract_api 同口径：
# Playwright 卡死时不能让这个项目的这个要件永远推不动。
STALE_SEC = 8 * 60

PUSH_KINDS = {
    "doc_confirm": {
        "label":         "采购文件确认函",
        "item_kind":     "content_confirm",   # archive_print.build_item 的 kind
        "material_type": "采购文件确认",
    },
    "auth_letter": {
        "label":         "授权函",
        "item_kind":     "auth_letter",
        "material_type": "采购人代表授权",
    },
    "result": {
        "label":         "采购结果确认函",
        "item_kind":     "result",
        "material_type": "采购结果确认函",
    },
}

# 采购项目审批的审批人（采购部主任）。存 SysConfig，换人不用改代码。
APPROVER_KEY = "rdweb_approval_approver"
DEFAULT_APPROVER = "曾旌城"


def get_approver() -> str:
    """这张单点给谁审批：采购部主任。"""
    try:
        from models import db
        from models.sys_config import SysConfig
        row = db.session.get(SysConfig, APPROVER_KEY)
        if row and (row.value or "").strip():
            return row.value.strip()
    except Exception:
        pass
    return DEFAULT_APPROVER


# 进程内状态：{(pid, kind): {running, ok, serial_no, msg, started_at}}
_state: dict = {}
_lock = threading.Lock()


def kind_meta(kind: str):
    return PUSH_KINDS.get(kind)


def get_status(pid: int, kind: str = "") -> dict:
    """取某项目某要件（或全部要件）的推送状态。"""
    with _lock:
        if kind:
            return dict(_state.get((pid, kind), {
                "running": False, "ok": None, "serial_no": "", "msg": ""}))
        return {k: dict(v) for (p, k), v in _state.items() if p == pid}


def _set(pid, kind, **kw):
    with _lock:
        _state[(pid, kind)] = kw


def _try_acquire(pid: int, kind: str):
    """占位成功返回 (True, "")；已有任务在跑返回 (False, 提示)。"""
    with _lock:
        st = _state.get((pid, kind), {})
        started = st.get("started_at", 0)
        stale = st.get("running") and started and (time.time() - started > STALE_SEC)
        if st.get("running") and not stale:
            waited = int(time.time() - started) if started else 0
            return False, f"该要件正在推送 rd-web（已 {waited} 秒），请稍后重试"
        _state[(pid, kind)] = {"running": True, "ok": None, "serial_no": "",
                               "msg": "提交中…", "started_at": time.time()}
    return True, ""


def _cn_round(n: int) -> str:
    return f"第{'一二三四五六七八九十'[n - 1]}次" if 1 <= n <= 10 else f"第{n}次"


def resolve_round(project, round_number=None) -> int:
    """默认推最新一轮：轮次是「第几次采购」，经办人刚确认的必然是最新那轮。"""
    from services.archive_print import _round_numbers
    if round_number:
        return int(round_number)
    nums = _round_numbers(project.id)
    return nums[-1] if nums else 1


def build_attachment(project, rno: int, kind: str):
    """生成该要件的 docx 临时文件，返回 [{"path","name"}]（生成不出来抛错）。

    rd-web 审批表单的附件是必填的，与其空着附件跑完两分钟再被表单挡下来，
    不如在这里就把「要件还没齐」说清楚。
    """
    from services.archive_print import build_item
    meta = PUSH_KINDS[kind]
    buf, label = build_item(project, rno, meta["item_kind"])
    if not buf:
        raise RuntimeError(
            f"{_cn_round(rno)}的「{meta['label']}」还生成不出来，"
            f"请先在对应步骤补齐要件（可在「11. 归档」页确认该要件能预览）。")
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tf:
        tf.write(buf.read())
        path = tf.name
    prefix = project.number or project.name or ""
    suffix = f"（{_cn_round(rno)}）" if rno > 1 else ""
    return [{"path": path, "name": f"{prefix}-{label or meta['label']}{suffix}.docx"}]


def project_name_text(project, rno: int) -> str:
    """rd-web 表单里的「项目名称」：多轮时带上第几次，避免几轮混在一起分不清。"""
    name = (project.name or "").strip()
    return f"{name}（{_cn_round(rno)}）" if rno > 1 else name


def already_pushed(pid: int, kind: str, rno: int) -> bool:
    """该项目该轮该要件是否已经成功推过（推送记录里查）。

    授权函这类「可以反复重新生成」的要件，若每次生成都自动推一次，
    rd-web 里会刷出一串重复单据——自动推送必须先看这一条，手动重推不受限。
    """
    from models import db
    from models.rdweb_push_log import RdwebPushLog
    q = (db.select(db.func.count()).select_from(RdwebPushLog)
         .filter(RdwebPushLog.status == "ok")
         .filter(RdwebPushLog.data_json.like(f'%"kind": "{kind}"%'))
         .filter(RdwebPushLog.data_json.like(f'%"项目ID": {pid},%'))
         .filter(RdwebPushLog.data_json.like(f'%"轮次": {rno},%')))
    return db.session.execute(q).scalar_one() > 0


def start_push(app, project, kind: str, officer: str, loginuser: str, password: str,
               round_number=None, manage_dept: str = "", username: str = "",
               display_name: str = "", skip_if_pushed: bool = False):
    """后台线程推送。返回 (ok, msg, round_number)；ok=False 时是没能启动的原因。"""
    meta = PUSH_KINDS.get(kind)
    if not meta:
        return False, f"未知的推送类型：{kind}", 0
    officer = (officer or "").strip()
    if not officer:
        return False, "项目没有经办人，无法确定审批填报的经办人", 0

    rno = resolve_round(project, round_number)
    approver = get_approver()
    if skip_if_pushed and already_pushed(project.id, kind, rno):
        return False, f"「{meta['label']}」本轮已成功推送过，未重复推送（可手动重推）", rno
    ok, why = _try_acquire(project.id, kind)
    if not ok:
        return False, why, rno

    # 预取项目数据，别把 ORM 对象带进线程（跨线程 lazy-load 会炸）
    pid = project.id
    pname_text = project_name_text(project, rno)
    dept = manage_dept or project.manage_dept or ""

    def _worker():
        tmp_path = None
        log_id = None
        try:
            from models import db
            from models.project import Project
            from models.rdweb_push_log import RdwebPushLog
            import datetime as _dt

            with app.app_context():
                p = db.session.get(Project, pid)
                attachments = build_attachment(p, rno, kind)
                tmp_path = attachments[0]["path"]
                log = RdwebPushLog(
                    username=username, display_name=display_name,
                    contract_name=f"{meta['label']}｜{pname_text}",
                    file_name=attachments[0]["name"][:200],
                    data_json=json.dumps({
                        "推送类型": meta["label"], "kind": kind, "项目ID": pid,
                        "轮次": rno, "项目名称": pname_text,
                        "归口管理科室": dept, "经办人": officer,
                        "审批人": approver,
                        "项目资料名称": meta["material_type"],
                    }, ensure_ascii=False),
                    status="running",
                )
                db.session.add(log)
                db.session.commit()
                log_id = log.id

            from services.procurement_approval_submit import submit_approval
            res = submit_approval(
                manage_dept=dept,
                project_name_text=pname_text,
                material_type=meta["material_type"],
                officer=officer,
                approver=approver,
                attachments=attachments,
                loginuser=loginuser,
                password=password,
            )
            r_ok, serial_no = bool(res.get("ok")), res.get("serial_no", "")
            msg = res.get("msg", "")
        except Exception as e:
            r_ok, serial_no, msg = False, "", str(e)[:300]

        _set(pid, kind, running=False, ok=r_ok, serial_no=serial_no,
             msg=msg, round_number=rno, finished_at=int(time.time()))

        if log_id:
            try:
                from models import db
                from models.rdweb_push_log import RdwebPushLog
                import datetime as _dt
                with app.app_context():
                    row = db.session.get(RdwebPushLog, log_id)
                    if row is not None:
                        row.status = "ok" if r_ok else "fail"
                        row.serial_no = serial_no
                        row.msg = (msg or "")[:500]
                        row.finished_at = _dt.datetime.now()
                        db.session.commit()
            except Exception as e:
                print(f"[rdweb-approval] 落库失败：{e}", flush=True)

        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()
    return True, f"已开始推送「{meta['label']}」到 rd-web 采购项目审批", rno
