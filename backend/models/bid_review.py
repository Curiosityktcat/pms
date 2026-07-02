"""投标文件 AI 审查（条目抽取 + 分阶段审查 + 评分/比价）。

业务流：创建任务 → 上传采购文件（OCR + LLM 抽取：评审方式/分包/标的概要 +
资格/实质性/商务/打分四类条目）→ 经办人编辑确认 → 逐份上传投标文件（选所投包）
→ 后台 OCR + LLM 一次跑完全部类别（判定类出 满足/不满足/未找到，打分项出建议分）
+ 抽总报价 → 结果按 资格审查/符合性审查/打分 三段展示，资格或符合性不满足提示
淘汰建议 → 人工复核改判/改分/改价 → 任务级汇总比价（综合评分法算价格分排总分，
最低评标价法按报价排序）→ 导出。

任务不强绑 pms 项目（task_name 自由输入，project_id 可空），兼容外部审标业务。
AI 仅做辅助定位与初判，最终判定以经办人人工复核为准。
价格分与淘汰结论不落库，由汇总端点按当前数据实时计算。
"""
import json

from models import db

# 条目类别（criteria.category 取值，按评审阶段排序）
CATEGORIES = ("资格", "实质性", "商务", "打分")
# 评审方式（task.eval_method 取值，空=未识别）
EVAL_METHODS = ("综合评分法", "最低评标价法")
# 不分包/通用条目的包号占位
LOT_COMMON = "通用"


def _loads(text, default):
    """容错解析 JSON 列，坏数据回落默认值。"""
    try:
        v = json.loads(text or "")
        return v if isinstance(v, type(default)) else default
    except Exception:
        return default


class BidReviewTask(db.Model):
    """审查任务（一个采购项目的一次评审）。"""
    __tablename__ = "bid_review_tasks"

    id         = db.Column(db.Integer, primary_key=True)
    task_name  = db.Column(db.String(300), nullable=False)   # 项目名称（自由输入）
    project_id = db.Column(db.Integer)                        # 可选关联 pms 项目（空=外部业务）

    # 状态机：draft → ocr_proc_doc → extracting → criteria_ready → done；任意环节 failed
    status     = db.Column(db.String(20), default="draft")
    error_msg  = db.Column(db.Text, default="")
    progress   = db.Column(db.String(50), default="")         # 抽取进度提示，如「抽取中 3/5」

    # 采购文件（条目清单的来源）
    proc_doc_name   = db.Column(db.String(300), default="")   # 原始文件名
    proc_doc_path   = db.Column(db.String(500), default="")   # 服务器存储路径
    proc_doc_ocr_md = db.Column(db.Text, default="")          # OCR markdown（含 <!--page:N--> 标记）

    # 评审方式与价格分（AI 识别，人工可改）
    eval_method     = db.Column(db.String(20), default="")    # 综合评分法|最低评标价法|空=未识别
    price_score_max = db.Column(db.String(20), default="")    # 价格分满分（文本容错，如「30」）
    price_formula   = db.Column(db.String(500), default="")   # 价格分计算规则原文（供人工核对）

    # 文件概要（JSON 列）
    lots_json    = db.Column(db.Text, default="[]")  # [{"lot_no","name","budget"}]；空=不分包
    summary_json = db.Column(db.Text, default="[]")  # [{"kind":"分包"|"标的","content","source_page"}]

    created_by = db.Column(db.String(50), default="")
    created_at = db.Column(db.String(30), default="")
    updated_at = db.Column(db.String(30), default="")

    @property
    def lots(self):
        return _loads(self.lots_json, [])

    def to_dict(self):
        return {
            "id": self.id, "task_name": self.task_name or "",
            "project_id": self.project_id,
            "status": self.status or "draft", "error_msg": self.error_msg or "",
            "progress": self.progress or "",
            "proc_doc_name": self.proc_doc_name or "",
            "has_proc_doc_ocr": bool(self.proc_doc_ocr_md),
            "eval_method": self.eval_method or "",
            "price_score_max": self.price_score_max or "",
            "price_formula": self.price_formula or "",
            "lots": self.lots,
            "summary": _loads(self.summary_json, []),
            "created_by": self.created_by or "",
            "created_at": self.created_at or "", "updated_at": self.updated_at or "",
        }


class BidReviewCriteria(db.Model):
    """条目清单（LLM 从采购文件抽取，经办人可增删改后确认）。

    seq 任务内全局唯一（扫描时 seq→id 映射依赖）；前端按分组内行号展示。
    """
    __tablename__ = "bid_review_criteria"

    id          = db.Column(db.Integer, primary_key=True)
    task_id     = db.Column(db.Integer, db.ForeignKey("bid_review_tasks.id"),
                            nullable=False, index=True)
    seq         = db.Column(db.Integer, default=1)            # 序号（任务内全局唯一）
    category    = db.Column(db.String(10), default="资格")    # 资格|实质性|商务|打分
    lot_no      = db.Column(db.String(30), default=LOT_COMMON)  # 适用包号；通用=全部包适用
    content     = db.Column(db.Text, default="")              # 条件/评分项全文
    max_score   = db.Column(db.Float)                         # 打分项满分（仅 category=打分）
    score_rule  = db.Column(db.Text, default="")              # 打分项评分细则原文
    source_page = db.Column(db.Integer)                       # 在采购文件的页码（可空）
    created_at  = db.Column(db.String(30), default="")

    def to_dict(self):
        return {
            "id": self.id, "task_id": self.task_id, "seq": self.seq or 1,
            "category": self.category or "资格",
            "lot_no": self.lot_no or LOT_COMMON,
            "content": self.content or "",
            "max_score": self.max_score, "score_rule": self.score_rule or "",
            "source_page": self.source_page,
            "created_at": self.created_at or "",
        }


class BidReviewResult(db.Model):
    """一个投标方的审查（每个投标方一条，可挂多个投标文件）。"""
    __tablename__ = "bid_review_results"

    id            = db.Column(db.Integer, primary_key=True)
    task_id       = db.Column(db.Integer, db.ForeignKey("bid_review_tasks.id"),
                              nullable=False, index=True)
    bid_file_name = db.Column(db.String(300), default="")     # 投标方名称（标签）
    file_path     = db.Column(db.String(500), default="")     # 兼容旧单文件；多文件见 files 子表
    ocr_md        = db.Column(db.Text, default="")            # 合并后全文（含连续页标记）
    lot_no        = db.Column(db.String(30), default=LOT_COMMON)  # 所投包号

    # 总报价（AI 抽取初值，人工可改；改后重跑审查不再覆盖）
    bid_price       = db.Column(db.String(50), default="")    # 数字串，如「1234567.00」
    price_page      = db.Column(db.String(30), default="")    # 报价出处，如「第3页」
    price_edited_by = db.Column(db.String(50), default="")    # 人工改价者（非空=锁定）

    ocr_status = db.Column(db.String(10), default="pending")  # pending|running|done|failed
    status     = db.Column(db.String(10), default="pending")  # AI 审查：pending|running|done|failed
    progress   = db.Column(db.String(20), default="")         # 进度提示，如「3/5 批」
    error_msg  = db.Column(db.Text, default="")

    created_at = db.Column(db.String(30), default="")
    updated_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {
            "id": self.id, "task_id": self.task_id,
            "bid_file_name": self.bid_file_name or "",
            "lot_no": self.lot_no or LOT_COMMON,
            "bid_price": self.bid_price or "",
            "price_page": self.price_page or "",
            "price_edited_by": self.price_edited_by or "",
            "ocr_status": self.ocr_status or "pending",
            "status": self.status or "pending",
            "progress": self.progress or "", "error_msg": self.error_msg or "",
            "created_at": self.created_at or "", "updated_at": self.updated_at or "",
        }


class BidReviewResultItem(db.Model):
    """逐条审查明细（一条条目 × 一份投标文件）。

    判定类（资格/实质性/商务）用 verdict；打分项用 ai_score/final_score，verdict 留空。
    """
    __tablename__ = "bid_review_result_items"

    id          = db.Column(db.Integer, primary_key=True)
    result_id   = db.Column(db.Integer, db.ForeignKey("bid_review_results.id"),
                            nullable=False, index=True)
    criteria_id = db.Column(db.Integer, db.ForeignKey("bid_review_criteria.id"),
                            nullable=False)

    verdict       = db.Column(db.String(10), default="")      # 满足|不满足|未找到（判定类）
    evidence_page = db.Column(db.String(30), default="")      # 如「第12页」「第12-14页」
    evidence_text = db.Column(db.Text, default="")            # 原文摘录（便于人工核对）
    confidence    = db.Column(db.String(5), default="")       # 高|中|低（模型自评）

    ai_score    = db.Column(db.Float)                         # 打分项 AI 建议分
    ai_reason   = db.Column(db.Text, default="")              # AI 评分理由
    final_score = db.Column(db.Float)                         # 最终得分（初值=ai_score，人工可改）

    note        = db.Column(db.Text, default="")              # 人工复核批注
    reviewed_by = db.Column(db.String(50), default="")        # 人工复核者（改判/改分/批注时记录）
    reviewed_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {
            "id": self.id, "result_id": self.result_id, "criteria_id": self.criteria_id,
            "verdict": self.verdict or "", "evidence_page": self.evidence_page or "",
            "evidence_text": self.evidence_text or "", "confidence": self.confidence or "",
            "ai_score": self.ai_score, "ai_reason": self.ai_reason or "",
            "final_score": self.final_score,
            "note": self.note or "", "reviewed_by": self.reviewed_by or "",
            "reviewed_at": self.reviewed_at or "",
        }


class BidReviewResultFile(db.Model):
    """一个投标方上传的单个文件（一个 result 可挂多个文件，审查时合并）。"""
    __tablename__ = "bid_review_result_files"

    id         = db.Column(db.Integer, primary_key=True)
    result_id  = db.Column(db.Integer, db.ForeignKey("bid_review_results.id"),
                           nullable=False, index=True)
    seq        = db.Column(db.Integer, default=1)            # 合并顺序
    file_name  = db.Column(db.String(300), default="")       # 原始文件名
    file_path  = db.Column(db.String(500), default="")       # 服务器存储路径
    created_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {
            "id": self.id, "result_id": self.result_id, "seq": self.seq or 1,
            "file_name": self.file_name or "", "created_at": self.created_at or "",
        }
