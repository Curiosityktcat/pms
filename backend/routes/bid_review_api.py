"""投标文件 AI 审查 API（条目抽取 + 分阶段审查 + 评分/比价）。

权限：经办人/助理/负责人可用；代理机构不可见（评审是采购人内部环节）。
长任务（OCR/LLM）走后台线程 + 状态轮询，见 services/bid_review.py。
价格分与淘汰结论不落库：/summary 端点按当前判定/得分/报价实时计算。
"""
import csv
import datetime
import io
import json
import os
import uuid

from flask import Blueprint, current_app, request, session, jsonify, send_file

from models import db
from models.bid_review import (
    BidReviewTask, BidReviewCriteria, BidReviewResult, BidReviewResultItem,
    BidReviewResultFile, CATEGORIES, EVAL_METHODS, LOT_COMMON,
)
from routes.utils import login_required
from services import bid_review as svc
from services import upload_relay

bp = Blueprint("bid_review", __name__, url_prefix="/api/bid-review")

UPLOAD_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "bid_review")
)
os.makedirs(UPLOAD_ROOT, exist_ok=True)

ALLOWED_EXTS = {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}

_CAT_ORDER = {c: i for i, c in enumerate(CATEGORIES)}


# 投标文件审核仅限白名单用户（默认仅「黄新博」）；可用 env BID_REVIEW_USERS 逗号分隔扩展。
BID_REVIEW_USERS = [u.strip() for u in os.environ.get(
    "BID_REVIEW_USERS", "黄新博").split(",") if u.strip()]


def _check_role():
    """投标文件审核：仅限白名单用户本人（默认仅 黄新博），其余人一律 403。"""
    return session.get("user", "") in BID_REVIEW_USERS


def _usage_ctx(feature="bid-review"):
    return {
        "username": session.get("user", ""),
        "display_name": session.get("display_name", ""),
        "feature": feature,
        "agency_code": "",   # 内部环节，不计代理费
    }


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _save_upload(task_id, f):
    """保存上传文件，返回 (存储路径, 原始文件名)；校验扩展名。"""
    _, ext = os.path.splitext(f.filename.lower())
    if ext == ".doc":
        raise ValueError("旧版 .doc 暂不支持，请用 Word 另存为 .docx 或 PDF 后上传")
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"不支持的文件格式：{ext}，支持 Word(.docx)/PDF/图片")
    d = os.path.join(UPLOAD_ROOT, str(task_id))
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{uuid.uuid4().hex}{ext}")
    f.save(path)
    return path, f.filename


def _result_dict(r):
    """投标方序列化，附带其文件清单与文件数。"""
    d = r.to_dict()
    files = db.session.execute(
        db.select(BidReviewResultFile).filter_by(result_id=r.id)
        .order_by(BidReviewResultFile.seq, BidReviewResultFile.id)
    ).scalars().all()
    # 兼容旧单文件 result（无子文件记录时用 file_path 占位展示）
    if not files and r.file_path:
        d["files"] = [{"id": 0, "file_name": r.bid_file_name or "（单文件）", "seq": 1}]
    else:
        d["files"] = [f.to_dict() for f in files]
    d["file_count"] = len(d["files"])
    return d


def _applicable_criteria(task, lot_no):
    """某投标文件适用的条目：通用+所投包；打分项仅综合评分法纳入。"""
    rows = db.session.execute(
        db.select(BidReviewCriteria).filter_by(task_id=task.id)
        .order_by(BidReviewCriteria.seq)).scalars().all()
    lot = lot_no or LOT_COMMON
    return [c for c in rows
            if (c.lot_no or LOT_COMMON) in (LOT_COMMON, lot)
            and (c.category != "打分" or task.eval_method == "综合评分法")]


@bp.before_request
def _guard():
    # login_required 在各端点上；这里统一卡角色（公开端点无）
    if request.method == "OPTIONS":
        return None
    if session.get("user") and not _check_role():
        return jsonify({"ok": False, "error": "投标文件审核功能未对当前账号开放"}), 403
    return None


# ── 任务 ───────────────────────────────────────────────────────────────
@bp.route("/tasks", methods=["GET"])
@login_required
def list_tasks():
    rows = db.session.execute(
        db.select(BidReviewTask).order_by(BidReviewTask.id.desc())
    ).scalars().all()
    # 批量挂条件数/投标文件数
    crit_cnt = dict(db.session.execute(
        db.select(BidReviewCriteria.task_id, db.func.count())
        .group_by(BidReviewCriteria.task_id)).all())
    res_cnt = dict(db.session.execute(
        db.select(BidReviewResult.task_id, db.func.count())
        .group_by(BidReviewResult.task_id)).all())
    out = []
    for t in rows:
        d = t.to_dict()
        d["criteria_count"] = crit_cnt.get(t.id, 0)
        d["result_count"] = res_cnt.get(t.id, 0)
        out.append(d)
    return jsonify({"ok": True, "data": out})


@bp.route("/tasks", methods=["POST"])
@login_required
def create_task():
    data = request.get_json(force=True) or {}
    name = (data.get("task_name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "请填写项目名称"}), 400
    t = BidReviewTask(
        task_name=name,
        project_id=data.get("project_id"),
        status="draft",
        created_by=session.get("display_name", ""),
        created_at=_now(), updated_at=_now(),
    )
    db.session.add(t)
    db.session.commit()
    return jsonify({"ok": True, "data": t.to_dict()}), 201


@bp.route("/tasks/<int:tid>", methods=["GET"])
@login_required
def get_task(tid):
    t = db.session.get(BidReviewTask, tid)
    if not t:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    d = t.to_dict()
    d["criteria"] = [c.to_dict() for c in db.session.execute(
        db.select(BidReviewCriteria).filter_by(task_id=tid)
        .order_by(BidReviewCriteria.seq)).scalars().all()]
    d["results"] = [_result_dict(r) for r in db.session.execute(
        db.select(BidReviewResult).filter_by(task_id=tid)
        .order_by(BidReviewResult.id)).scalars().all()]
    return jsonify({"ok": True, "data": d})


@bp.route("/tasks/<int:tid>", methods=["PUT"])
@login_required
def update_task(tid):
    """人工修正概要：评审方式 / 价格分 / 分包清单 / 概要条目。"""
    t = db.session.get(BidReviewTask, tid)
    if not t:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    data = request.get_json(force=True) or {}
    if "eval_method" in data:
        m = (data.get("eval_method") or "").strip()
        if m and m not in EVAL_METHODS:
            return jsonify({"ok": False,
                            "error": "评审方式只能是 综合评分法/最低评标价法"}), 400
        t.eval_method = m
    if "price_score_max" in data:
        t.price_score_max = str(data.get("price_score_max") or "").strip()[:20]
    if "price_formula" in data:
        t.price_formula = (data.get("price_formula") or "").strip()[:500]
    if "lots" in data:
        lots = data.get("lots")
        if not isinstance(lots, list):
            return jsonify({"ok": False, "error": "分包清单格式错误"}), 400
        clean = []
        for l in lots:
            if isinstance(l, dict) and str(l.get("lot_no") or "").strip():
                clean.append({
                    "lot_no": str(l.get("lot_no")).strip()[:30],
                    "name": str(l.get("name") or "").strip()[:200],
                    "budget": str(l.get("budget") or "").strip()[:100],
                })
        t.lots_json = json.dumps(clean, ensure_ascii=False)
    if "summary" in data and isinstance(data.get("summary"), list):
        t.summary_json = json.dumps(data["summary"], ensure_ascii=False)
    t.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "data": t.to_dict()})


@bp.route("/tasks/<int:tid>", methods=["DELETE"])
@login_required
def delete_task(tid):
    t = db.session.get(BidReviewTask, tid)
    if not t:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    rids = [r.id for r in db.session.execute(
        db.select(BidReviewResult).filter_by(task_id=tid)).scalars().all()]
    if rids:
        db.session.execute(db.delete(BidReviewResultItem).where(
            BidReviewResultItem.result_id.in_(rids)))
        db.session.execute(db.delete(BidReviewResultFile).where(
            BidReviewResultFile.result_id.in_(rids)))
        db.session.execute(db.delete(BidReviewResult).where(
            BidReviewResult.id.in_(rids)))
    db.session.execute(db.delete(BidReviewCriteria).where(
        BidReviewCriteria.task_id == tid))
    db.session.delete(t)
    db.session.commit()
    # 清理上传目录
    import shutil
    shutil.rmtree(os.path.join(UPLOAD_ROOT, str(tid)), ignore_errors=True)
    return jsonify({"ok": True, "message": "已删除"})


@bp.route("/tasks/<int:tid>/status", methods=["GET"])
@login_required
def task_status(tid):
    t = db.session.get(BidReviewTask, tid)
    if not t:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    crit_n = db.session.execute(
        db.select(db.func.count()).select_from(BidReviewCriteria)
        .filter_by(task_id=tid)).scalar_one()
    return jsonify({"ok": True, "data": {
        "status": t.status, "error_msg": t.error_msg or "",
        "progress": t.progress or "",
        "criteria_count": crit_n,
    }})


# ── 采购文件上传 → 触发 OCR + 抽取 ────────────────────────────────────
@bp.route("/tasks/<int:tid>/proc-doc", methods=["POST"])
@login_required
def upload_proc_doc(tid):
    t = db.session.get(BidReviewTask, tid)
    if not t:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    if t.status in ("ocr_proc_doc", "extracting"):
        return jsonify({"ok": False, "error": "采购文件正在处理中，请稍候"}), 400
    f = request.files.get("file") or upload_relay.staged_file()  # 公网大文件走 OSS 中转（见 services/upload_relay.py）
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未收到文件"}), 400
    try:
        path, name = _save_upload(tid, f)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    t.proc_doc_path = path
    t.proc_doc_name = name
    t.proc_doc_ocr_md = ""     # 重传时清旧 OCR
    t.updated_at = _now()
    db.session.commit()
    svc.start_proc_doc_thread(
        current_app._get_current_object(), tid, _usage_ctx())
    return jsonify({"ok": True, "message": "已开始识别采购文件并抽取条目，请稍候刷新"})


# ── 条目 CRUD ─────────────────────────────────────────────────────────
def _apply_criteria_fields(c, data):
    """校验并写入条目可编辑字段，返回错误信息（None=成功）。"""
    if "content" in data:
        content = (data.get("content") or "").strip()
        if not content:
            return "条目内容不能为空"
        c.content = content
    if "category" in data:
        cat = (data.get("category") or "").strip()
        if cat not in CATEGORIES:
            return "类别只能是 资格/实质性/商务/打分"
        c.category = cat
    if "lot_no" in data:
        c.lot_no = (str(data.get("lot_no") or "").strip() or LOT_COMMON)[:30]
    if "max_score" in data:
        ms = data.get("max_score")
        if ms in (None, ""):
            c.max_score = None
        else:
            try:
                ms = float(ms)
            except (TypeError, ValueError):
                return "分值必须是数字"
            if ms <= 0:
                return "分值必须大于 0"
            c.max_score = ms
    if "score_rule" in data:
        c.score_rule = (data.get("score_rule") or "").strip()
    if "seq" in data:
        c.seq = int(data.get("seq") or c.seq)
    if c.category == "打分" and c.max_score is None:
        return "打分项必须填写分值"
    return None


@bp.route("/tasks/<int:tid>/criteria", methods=["POST"])
@login_required
def add_criteria(tid):
    if not db.session.get(BidReviewTask, tid):
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    data = request.get_json(force=True) or {}
    if not (data.get("content") or "").strip():
        return jsonify({"ok": False, "error": "条目内容不能为空"}), 400
    max_seq = db.session.execute(
        db.select(db.func.max(BidReviewCriteria.seq)).filter_by(task_id=tid)
    ).scalar() or 0
    c = BidReviewCriteria(task_id=tid, seq=max_seq + 1,
                          source_page=data.get("source_page"), created_at=_now())
    err = _apply_criteria_fields(c, data)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    db.session.add(c)
    db.session.commit()
    return jsonify({"ok": True, "data": c.to_dict()}), 201


@bp.route("/tasks/<int:tid>/criteria/<int:cid>", methods=["PUT"])
@login_required
def update_criteria(tid, cid):
    c = db.session.get(BidReviewCriteria, cid)
    if not c or c.task_id != tid:
        return jsonify({"ok": False, "error": "条目不存在"}), 404
    err = _apply_criteria_fields(c, request.get_json(force=True) or {})
    if err:
        db.session.rollback()
        return jsonify({"ok": False, "error": err}), 400
    db.session.commit()
    return jsonify({"ok": True, "data": c.to_dict()})


@bp.route("/tasks/<int:tid>/criteria/<int:cid>", methods=["DELETE"])
@login_required
def delete_criteria(tid, cid):
    c = db.session.get(BidReviewCriteria, cid)
    if not c or c.task_id != tid:
        return jsonify({"ok": False, "error": "条目不存在"}), 404
    db.session.execute(db.delete(BidReviewResultItem).where(
        BidReviewResultItem.criteria_id == cid))
    db.session.delete(c)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})


# ── 投标文件 ──────────────────────────────────────────────────────────
def _add_files(tid, rid, files, start_seq=1):
    """保存多个文件为 result 的子文件记录（存到任务目录），返回 (已保存数, 错误信息)。"""
    saved = 0
    for i, f in enumerate(files):
        if not f or not f.filename:
            continue
        try:
            path, name = _save_upload(tid, f)
        except ValueError as e:
            return saved, str(e)
        db.session.add(BidReviewResultFile(
            result_id=rid, seq=start_seq + i, file_name=name,
            file_path=path, created_at=_now()))
        saved += 1
    return saved, None


@bp.route("/tasks/<int:tid>/results", methods=["POST"])
@login_required
def add_result(tid):
    """新建投标方：填名称+所投包，一次上传该投标方的全部文件。"""
    t = db.session.get(BidReviewTask, tid)
    if not t:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    lot_no = (request.form.get("lot_no") or "").strip() or LOT_COMMON
    lots = t.lots
    if lots:
        valid = {l.get("lot_no") for l in lots}
        if lot_no not in valid:
            return jsonify({"ok": False, "error": "请选择所投包号"}), 400
    if not _applicable_criteria(t, lot_no):
        return jsonify({"ok": False,
                        "error": "适用该包的条目清单为空，请先上传采购文件并确认条目"}), 400
    files = [f for f in request.files.getlist("file") if f and f.filename]
    if not files:
        return jsonify({"ok": False, "error": "请至少上传一个投标文件"}), 400
    label = (request.form.get("label") or "").strip() or files[0].filename
    # 先建投标方拿到 id（文件存到以 result_id 命名的目录）
    r = BidReviewResult(task_id=tid, bid_file_name=label, lot_no=lot_no,
                        created_at=_now(), updated_at=_now())
    db.session.add(r)
    db.session.flush()
    saved, err = _add_files(tid, r.id, files)
    if err:
        db.session.rollback()
        return jsonify({"ok": False, "error": err}), 400
    db.session.commit()
    return jsonify({"ok": True, "data": _result_dict(r),
                    "message": f"已创建投标方「{label}」，上传 {saved} 个文件"}), 201


@bp.route("/tasks/<int:tid>/results/<int:rid>/files", methods=["POST"])
@login_required
def add_result_files(tid, rid):
    """给已有投标方追加文件（清空已识别文本，下次审查重新合并）。"""
    r = db.session.get(BidReviewResult, rid)
    if not r or r.task_id != tid:
        return jsonify({"ok": False, "error": "投标方不存在"}), 404
    if r.status == "running" or r.ocr_status == "running":
        return jsonify({"ok": False, "error": "审查进行中，无法添加文件"}), 400
    files = [f for f in request.files.getlist("file") if f and f.filename]
    if not files:
        return jsonify({"ok": False, "error": "未收到文件"}), 400
    max_seq = db.session.execute(
        db.select(db.func.max(BidReviewResultFile.seq)).filter_by(result_id=rid)
    ).scalar() or 0
    saved, err = _add_files(tid, rid, files, start_seq=max_seq + 1)
    if err:
        db.session.rollback()
        return jsonify({"ok": False, "error": err}), 400
    r.ocr_md = ""   # 文件变更 → 作废旧合并文本，强制重新识别
    r.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "message": f"已追加 {saved} 个文件，请重新审查"})


@bp.route("/tasks/<int:tid>/results/<int:rid>/files/<int:fid>", methods=["DELETE"])
@login_required
def delete_result_file(tid, rid, fid):
    r = db.session.get(BidReviewResult, rid)
    if not r or r.task_id != tid:
        return jsonify({"ok": False, "error": "投标方不存在"}), 404
    if r.status == "running" or r.ocr_status == "running":
        return jsonify({"ok": False, "error": "审查进行中，无法删除文件"}), 400
    f = db.session.get(BidReviewResultFile, fid)
    if not f or f.result_id != rid:
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    try:
        if f.file_path and os.path.exists(f.file_path):
            os.remove(f.file_path)
    except Exception:
        pass
    db.session.delete(f)
    r.ocr_md = ""   # 文件变更 → 作废旧合并文本
    r.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除该文件，请重新审查"})


@bp.route("/tasks/<int:tid>/results/<int:rid>", methods=["PUT"])
@login_required
def update_result(tid, rid):
    """人工修正：总报价（记改价人，重跑不再覆盖）/ 所投包号。"""
    r = db.session.get(BidReviewResult, rid)
    if not r or r.task_id != tid:
        return jsonify({"ok": False, "error": "投标文件不存在"}), 404
    data = request.get_json(force=True) or {}
    if "bid_price" in data:
        price = str(data.get("bid_price") or "").strip().replace(",", "")
        if price:
            try:
                float(price)
            except ValueError:
                return jsonify({"ok": False, "error": "报价必须是数字（单位：元）"}), 400
        r.bid_price = price
        r.price_edited_by = session.get("display_name", "")
    if "lot_no" in data:
        if r.status == "running" or r.ocr_status == "running":
            return jsonify({"ok": False, "error": "审查进行中，无法改包号"}), 400
        r.lot_no = (str(data.get("lot_no") or "").strip() or LOT_COMMON)[:30]
    r.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "data": r.to_dict()})


@bp.route("/tasks/<int:tid>/results/<int:rid>", methods=["DELETE"])
@login_required
def delete_result(tid, rid):
    r = db.session.get(BidReviewResult, rid)
    if not r or r.task_id != tid:
        return jsonify({"ok": False, "error": "投标文件不存在"}), 404
    if r.status == "running" or r.ocr_status == "running":
        return jsonify({"ok": False, "error": "正在审查中，无法删除"}), 400
    db.session.execute(db.delete(BidReviewResultItem).where(
        BidReviewResultItem.result_id == rid))
    # 删除子文件记录及磁盘文件（含兼容旧单文件 file_path）
    child_files = db.session.execute(
        db.select(BidReviewResultFile).filter_by(result_id=rid)).scalars().all()
    for cf in child_files:
        try:
            if cf.file_path and os.path.exists(cf.file_path):
                os.remove(cf.file_path)
        except Exception:
            pass
    db.session.execute(db.delete(BidReviewResultFile).where(
        BidReviewResultFile.result_id == rid))
    try:
        if r.file_path and os.path.exists(r.file_path):
            os.remove(r.file_path)
    except Exception:
        pass
    db.session.delete(r)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})


@bp.route("/tasks/<int:tid>/results/<int:rid>/start", methods=["POST"])
@login_required
def start_review(tid, rid):
    r = db.session.get(BidReviewResult, rid)
    if not r or r.task_id != tid:
        return jsonify({"ok": False, "error": "投标文件不存在"}), 404
    if r.status == "running" or r.ocr_status == "running":
        return jsonify({"ok": False, "error": "该文件正在审查中"}), 400
    r.status = "pending"
    r.progress = ""
    r.error_msg = ""
    db.session.commit()
    svc.start_review_thread(
        current_app._get_current_object(), rid, _usage_ctx())
    return jsonify({"ok": True, "message": "已开始审查，请稍候查看进度"})


@bp.route("/tasks/<int:tid>/results/<int:rid>/status", methods=["GET"])
@login_required
def result_status(tid, rid):
    r = db.session.get(BidReviewResult, rid)
    if not r or r.task_id != tid:
        return jsonify({"ok": False, "error": "投标文件不存在"}), 404
    return jsonify({"ok": True, "data": r.to_dict()})


@bp.route("/tasks/<int:tid>/results/<int:rid>/items", methods=["GET"])
@login_required
def list_items(tid, rid):
    r = db.session.get(BidReviewResult, rid)
    if not r or r.task_id != tid:
        return jsonify({"ok": False, "error": "投标文件不存在"}), 404
    crit = {c.id: c for c in db.session.execute(
        db.select(BidReviewCriteria).filter_by(task_id=tid)).scalars().all()}
    items = db.session.execute(
        db.select(BidReviewResultItem).filter_by(result_id=rid)
    ).scalars().all()
    out = []
    for it in items:
        d = it.to_dict()
        c = crit.get(it.criteria_id)
        d["criteria_seq"] = c.seq if c else 0
        d["criteria_content"] = c.content if c else ""
        d["category"] = (c.category if c else "") or "资格"
        d["lot_no"] = (c.lot_no if c else "") or LOT_COMMON
        d["max_score"] = c.max_score if c else None
        d["score_rule"] = (c.score_rule if c else "") or ""
        out.append(d)
    out.sort(key=lambda x: (_CAT_ORDER.get(x["category"], 9), x["criteria_seq"]))
    return jsonify({"ok": True, "data": out})


@bp.route("/tasks/<int:tid>/results/<int:rid>/items/<int:iid>", methods=["PUT"])
@login_required
def update_item(tid, rid, iid):
    """人工复核：判定类改判 / 打分项改最终得分 / 加批注（记录复核人与时间）。"""
    it = db.session.get(BidReviewResultItem, iid)
    if not it or it.result_id != rid:
        return jsonify({"ok": False, "error": "判定项不存在"}), 404
    c = db.session.get(BidReviewCriteria, it.criteria_id)
    is_score = bool(c and c.category == "打分")
    data = request.get_json(force=True) or {}
    if "verdict" in data:
        if is_score:
            return jsonify({"ok": False, "error": "打分项请修改最终得分，不能改判定"}), 400
        v = (data.get("verdict") or "").strip()
        if v not in ("满足", "不满足", "需核验", "未找到"):
            return jsonify({"ok": False, "error": "判定只能是 满足/不满足/需核验/未找到"}), 400
        it.verdict = v
    if "final_score" in data:
        if not is_score:
            return jsonify({"ok": False, "error": "仅打分项可填得分"}), 400
        fs = data.get("final_score")
        if fs in (None, ""):
            it.final_score = None
        else:
            try:
                fs = float(fs)
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "得分必须是数字"}), 400
            if fs < 0 or (c.max_score is not None and fs > c.max_score):
                return jsonify({"ok": False,
                                "error": f"得分须在 0~{c.max_score:g} 之间"}), 400
            it.final_score = fs
    if "note" in data:
        it.note = (data.get("note") or "").strip()
    it.reviewed_by = session.get("display_name", "")
    it.reviewed_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "data": it.to_dict()})


# ── 任务级汇总/比价 ───────────────────────────────────────────────────
def _result_stats(crit, result_id):
    """单个投标文件的审查统计（按条目类别归集）。"""
    items = db.session.execute(
        db.select(BidReviewResultItem).filter_by(result_id=result_id)
    ).scalars().all()
    qual_fails, qual_unfound, qual_review = [], [], []
    comp_fails, comp_unfound, comp_review = [], [], []
    tech_score = 0.0
    for it in items:
        c = crit.get(it.criteria_id)
        if not c:
            continue
        if c.category == "打分":
            tech_score += it.final_score or 0
        elif c.category == "资格":
            if it.verdict == "不满足":
                qual_fails.append(c.seq)
            elif it.verdict == "需核验":
                qual_review.append(c.seq)
            elif it.verdict == "未找到":
                qual_unfound.append(c.seq)
        else:   # 实质性/商务 → 符合性
            if it.verdict == "不满足":
                comp_fails.append(c.seq)
            elif it.verdict == "需核验":
                comp_review.append(c.seq)
            elif it.verdict == "未找到":
                comp_unfound.append(c.seq)
    return {
        "qual_fails": sorted(qual_fails), "qual_unfound": sorted(qual_unfound),
        "qual_review": sorted(qual_review),
        "compliance_fails": sorted(comp_fails),
        "compliance_unfound": sorted(comp_unfound),
        "compliance_review": sorted(comp_review),
        "tech_score": round(tech_score, 2),
    }


def _compute_summary(t):
    """汇总/比价：按包分组实时计算价格分、总分、排名与淘汰建议。

    价格分 = 最低有效报价 / 该家报价 × 价格分满分（仅合规且有报价者参与）。
    淘汰者与缺报价者列出但不参与基准与排名。
    """
    crit = {c.id: c for c in db.session.execute(
        db.select(BidReviewCriteria).filter_by(task_id=t.id)).scalars().all()}
    results = [r for r in db.session.execute(
        db.select(BidReviewResult).filter_by(task_id=t.id)
        .order_by(BidReviewResult.id)).scalars().all() if r.status == "done"]

    try:
        psm = float(t.price_score_max)
    except (TypeError, ValueError):
        psm = None

    by_lot = {}
    for r in results:
        stats = _result_stats(crit, r.id)
        try:
            price = float((r.bid_price or "").replace(",", ""))
        except ValueError:
            price = None
        eliminated = ("资格性淘汰" if stats["qual_fails"]
                      else "符合性淘汰" if stats["compliance_fails"] else "")
        row = {
            "result_id": r.id, "bid_file_name": r.bid_file_name,
            "lot_no": r.lot_no or LOT_COMMON,
            "bid_price": price, "price_edited_by": r.price_edited_by or "",
            "eliminated": eliminated,
            "price_score": None, "total": None, "rank": None,
            **stats,
        }
        by_lot.setdefault(row["lot_no"], []).append(row)

    groups = []
    for lot in sorted(by_lot):
        rows = by_lot[lot]
        valid = [x for x in rows if not x["eliminated"] and x["bid_price"]]
        if t.eval_method == "综合评分法":
            base = min((x["bid_price"] for x in valid), default=None)
            for x in valid:
                if base and psm:
                    x["price_score"] = round(base / x["bid_price"] * psm, 2)
                    x["total"] = round(x["tech_score"] + x["price_score"], 2)
            ranked = sorted([x for x in valid if x["total"] is not None],
                            key=lambda x: -x["total"])
        else:   # 最低评标价法（或未定方式按报价排序兜底）
            ranked = sorted(valid, key=lambda x: x["bid_price"])
        for i, x in enumerate(ranked, 1):
            x["rank"] = i
        rows.sort(key=lambda x: (x["rank"] or 9999, x["result_id"]))
        groups.append({"lot_no": lot, "rows": rows})

    return {
        "eval_method": t.eval_method or "",
        "price_score_max": t.price_score_max or "",
        "price_formula": t.price_formula or "",
        "groups": groups,
    }


@bp.route("/tasks/<int:tid>/summary", methods=["GET"])
@login_required
def task_summary(tid):
    t = db.session.get(BidReviewTask, tid)
    if not t:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    return jsonify({"ok": True, "data": _compute_summary(t)})


# ── 导出 CSV ──────────────────────────────────────────────────────────
def _csv_response(buf, filename):
    data = ("﻿" + buf.getvalue()).encode("utf-8")   # BOM 让 Excel 正确识别中文
    return send_file(io.BytesIO(data), mimetype="text/csv", as_attachment=True,
                     download_name=filename)


@bp.route("/tasks/<int:tid>/results/<int:rid>/export", methods=["GET"])
@login_required
def export_csv(tid, rid):
    t = db.session.get(BidReviewTask, tid)
    r = db.session.get(BidReviewResult, rid)
    if not t or not r or r.task_id != tid:
        return jsonify({"ok": False, "error": "数据不存在"}), 404
    crit = {c.id: c for c in db.session.execute(
        db.select(BidReviewCriteria).filter_by(task_id=tid)).scalars().all()}
    items = sorted(
        db.session.execute(db.select(BidReviewResultItem)
                           .filter_by(result_id=rid)).scalars().all(),
        key=lambda x: (_CAT_ORDER.get(crit[x.criteria_id].category, 9)
                       if x.criteria_id in crit else 9,
                       crit[x.criteria_id].seq if x.criteria_id in crit else 0))
    stats = _result_stats(crit, rid)
    eliminated = ("建议资格性淘汰" if stats["qual_fails"]
                  else "建议符合性淘汰" if stats["compliance_fails"] else "初判通过")

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"投标文件审查表（AI 辅助）— {t.task_name}"])
    w.writerow([f"投标文件：{r.bid_file_name}", f"包号：{r.lot_no or LOT_COMMON}",
                f"评审方式：{t.eval_method or '未设置'}",
                f"总报价：{r.bid_price or '—'}", f"淘汰建议：{eliminated}",
                f"导出时间：{_now()}", "注：AI 结果仅供参考，以经办人复核为准"])

    def _judge_rows(cats, title, with_cat):
        rows = [it for it in items
                if crit.get(it.criteria_id) and crit[it.criteria_id].category in cats]
        if not rows:
            return
        w.writerow([])
        w.writerow([title])
        head = ["序号", "条目"] + (["类别"] if with_cat else []) + \
               ["判定", "证据页码", "原文摘录", "置信度", "人工批注", "复核人"]
        w.writerow(head)
        for it in rows:
            c = crit[it.criteria_id]
            line = [c.seq, c.content] + ([c.category] if with_cat else []) + \
                   [it.verdict, it.evidence_page, it.evidence_text,
                    it.confidence, it.note, it.reviewed_by]
            w.writerow(line)

    _judge_rows(("资格",), "一、资格审查", with_cat=False)
    _judge_rows(("实质性", "商务"), "二、符合性审查（实质性+商务）", with_cat=True)

    score_rows = [it for it in items
                  if crit.get(it.criteria_id) and crit[it.criteria_id].category == "打分"]
    if score_rows:
        w.writerow([])
        w.writerow(["三、评分明细（不含价格分）"])
        w.writerow(["序号", "评分项", "分值", "评分规则", "AI建议分", "AI理由",
                    "最终得分", "证据页码", "人工批注", "复核人"])
        total = 0.0
        for it in score_rows:
            c = crit[it.criteria_id]
            total += it.final_score or 0
            w.writerow([c.seq, c.content,
                        f"{c.max_score:g}" if c.max_score is not None else "",
                        c.score_rule, it.ai_score, it.ai_reason, it.final_score,
                        it.evidence_page, it.note, it.reviewed_by])
        w.writerow(["", "合计", "", "", "", "", round(total, 2), "", "", ""])

    return _csv_response(buf, f"审查表_{r.bid_file_name}.csv")


@bp.route("/tasks/<int:tid>/export-summary", methods=["GET"])
@login_required
def export_summary_csv(tid):
    t = db.session.get(BidReviewTask, tid)
    if not t:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    s = _compute_summary(t)
    is_score = t.eval_method == "综合评分法"

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"评审汇总表（AI 辅助）— {t.task_name}"])
    w.writerow([f"评审方式：{t.eval_method or '未设置'}",
                f"价格分满分：{s['price_score_max'] or '—'}" if is_score else "",
                f"导出时间：{_now()}", "注：AI 结果仅供参考，以评审人员复核为准"])
    for g in s["groups"]:
        w.writerow([])
        w.writerow([f"包号：{g['lot_no']}"])
        if is_score:
            w.writerow(["排名", "投标方", "总报价(元)", "资格审查", "符合性审查",
                        "技术商务分", "价格分", "总分", "淘汰建议"])
        else:
            w.writerow(["排名", "投标方", "总报价(元)", "资格审查", "符合性审查", "淘汰建议"])
        for x in g["rows"]:
            qual = ("不满足:" + ",".join(map(str, x["qual_fails"]))
                    if x["qual_fails"] else "通过")
            comp = ("不满足:" + ",".join(map(str, x["compliance_fails"]))
                    if x["compliance_fails"] else "通过")
            base = [x["rank"] or "—", x["bid_file_name"], x["bid_price"] or "—",
                    qual, comp]
            if is_score:
                base += [x["tech_score"], x["price_score"] or "—", x["total"] or "—"]
            base.append(x["eliminated"] or "")
            w.writerow(base)
    return _csv_response(buf, f"评审汇总_{t.task_name}.csv")
