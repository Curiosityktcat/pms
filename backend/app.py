import os
from datetime import timedelta
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from models import db


def create_app():
    app = Flask(__name__)

    here = os.path.dirname(os.path.abspath(__file__))
    # 数据库与前端目录可由环境变量覆盖（测试实例用），默认即正式环境路径
    db_path = os.environ.get("PMS_DB_PATH") or os.path.abspath(
        os.path.join(here, "..", "pms.db")
    )
    dist_path = os.environ.get("PMS_DIST") or os.path.abspath(
        os.path.join(here, "..", "frontend", "dist")
    )

    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    # 文件库大文件上传：上限 5GB（文件流式落盘，不占内存）
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024 * 1024
    app.config["MAX_FORM_MEMORY_SIZE"] = None  # 不限制表单内存（文件部分仍落盘）
    # 会话密钥：优先取环境变量 PMS_SECRET_KEY；迁移到新机时务必设置随机强密钥
    # （export PMS_SECRET_KEY=$(openssl rand -hex 32)），否则会话可被伪造。
    app.config["SECRET_KEY"] = os.environ.get("PMS_SECRET_KEY", "change-this-secret-key-please")
    # 会话空闲超时：30 分钟无请求即失效，需重新登录（兜底；前端另有基于用户操作的空闲计时器）。
    # SESSION_REFRESH_EACH_REQUEST=True 时每次请求都会刷新 cookie 时间戳，实现“滑动”空闲过期。
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True

    db.init_app(app)

    # 开发模式允许跨域；生产模式前端由 Flask 直接提供，不需要跨域
    CORS(app, supports_credentials=True, origins=["http://localhost:5173"])

    from routes.auth_api import bp as auth_bp
    from routes.project_api import bp as project_bp
    from routes.bid_api import bp as bid_bp
    from routes.people_api import bp as people_bp
    from routes.auth_letter_api import bp as auth_letter_bp
    from routes.announcement_api import bp as announcement_bp
    from routes.agency_template_api import bp as agency_template_bp
    from routes.auth_letter_record_api import bp as auth_letter_record_bp
    from routes.procurement_demand_api import bp as procurement_demand_bp
    from routes.procurement_result_api import bp as procurement_result_bp
    from routes.contract_api import bp as contract_bp
    from routes.internal_bid_demand_api import bp as internal_bid_demand_bp
    from routes.inquiry_api import bp as inquiry_bp
    from routes.inquiry_review_api import bp as inquiry_review_bp
    from routes.inbox_api import bp as inbox_bp
    from routes.chat_api import bp as chat_bp
    from routes.ccgp_api import bp as ccgp_bp
    from routes.doc_form_api import bp as doc_form_bp
    from routes.bid_board_api import bp as bid_board_bp
    from routes.permission_api import bp as permission_bp
    from routes.agency_agreement_api import bp as agency_agreement_bp
    from routes.my_template_api import bp as my_template_bp  # 我的模板库（按用户隔离）
    from routes.procurement_doc_api import bp as procurement_doc_bp
    from routes.template_api import bp as template_bp
    from routes.archive_api import bp as archive_bp
    from routes.llm_usage_api import bp as llm_usage_bp
    from routes.ocr_api import bp as ocr_bp
    from routes.bid_review_api import bp as bid_review_bp
    from routes.filebox_api import bp as filebox_bp
    from routes.datapipe_api import bp as datapipe_bp   # 政采数据流水线看板（仅黄新博）
    from routes.presence_api import bp as presence_bp
    from routes.supervision_api import bp as supervision_bp  # 投诉质疑数据库
    from routes.dept_announcement_api import bp as dept_announcement_bp  # 采购部公告
    from routes.tools_doc_gen_api import bp as tools_doc_gen_bp  # AI采购文件生成工具
    from models.dept_announcement import DeptAnnouncement  # noqa: F401 建表用
    from routes.law_api import bp as law_bp  # 法规库
    from routes.sysdocs_api import bp as sysdocs_bp  # 系统说明书/更新日志
    from routes.project_distribution_api import bp as project_distribution_bp  # 采购项目分发
    from routes.project_review_api import bp as project_review_bp  # 8.5 项目评审资料上传
    from routes.ai_assistant_api import bp as ai_assistant_bp  # 耗子AI助手
    from routes.hermes_api import bp as hermes_bp  # 指挥 Hermes 自动填报 rd-web
    from routes.agency_api import bp as agency_bp  # 代理机构信息维护
    from routes.rdweb_contract_api import bp as rdweb_contract_bp  # rd-web 合同审签单直连自动提交
    from routes.rdweb_approval_api import bp as rdweb_approval_bp  # rd-web 采购项目审批要件推送
    from routes.api_provider_api import bp as api_provider_bp  # 后台 API 管理（大模型台账）
    from routes.agency_assessment_api import bp as agency_assessment_bp  # 代理机构服务质量考核
    from routes.procurement_plan_api import bp as procurement_plan_bp     # 采购计划池（归口科室年度计划）
    from routes.web_announcement_api import bp as web_announcement_bp     # 官网公告存档（只读）
    from routes.doc_intake_attach_api import bp as doc_intake_attach_bp  # 归档资料自动挂载
    from routes.auth_letter_pending_api import bp as auth_letter_pending_bp  # 待出具授权函清单

    app.register_blueprint(auth_bp)
    app.register_blueprint(project_bp)
    app.register_blueprint(bid_bp)
    app.register_blueprint(people_bp)
    app.register_blueprint(auth_letter_bp)
    app.register_blueprint(announcement_bp)
    app.register_blueprint(agency_template_bp)
    app.register_blueprint(auth_letter_record_bp)
    app.register_blueprint(procurement_demand_bp)
    app.register_blueprint(procurement_result_bp)
    app.register_blueprint(contract_bp)
    app.register_blueprint(internal_bid_demand_bp)
    app.register_blueprint(inquiry_bp)
    app.register_blueprint(inquiry_review_bp)
    app.register_blueprint(inbox_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(ccgp_bp)
    app.register_blueprint(doc_form_bp)
    app.register_blueprint(bid_board_bp)
    app.register_blueprint(permission_bp)
    app.register_blueprint(agency_agreement_bp)
    app.register_blueprint(procurement_doc_bp)
    app.register_blueprint(template_bp)
    app.register_blueprint(archive_bp)
    app.register_blueprint(llm_usage_bp)
    app.register_blueprint(ocr_bp)
    app.register_blueprint(bid_review_bp)
    app.register_blueprint(filebox_bp)
    app.register_blueprint(datapipe_bp)
    app.register_blueprint(presence_bp)
    app.register_blueprint(supervision_bp)
    app.register_blueprint(dept_announcement_bp)
    app.register_blueprint(tools_doc_gen_bp)
    app.register_blueprint(my_template_bp)
    app.register_blueprint(law_bp)
    app.register_blueprint(sysdocs_bp)
    app.register_blueprint(project_distribution_bp)
    app.register_blueprint(project_review_bp)
    app.register_blueprint(ai_assistant_bp)  # 耗子AI助手
    app.register_blueprint(hermes_bp)  # Hermes 自动填报
    app.register_blueprint(agency_bp)  # 代理机构信息维护
    app.register_blueprint(rdweb_contract_bp)  # rd-web 合同审签单直连
    app.register_blueprint(rdweb_approval_bp)  # rd-web 采购项目审批：文件确认函/授权函/结果确认函推送
    app.register_blueprint(api_provider_bp)  # 后台 API 管理
    app.register_blueprint(agency_assessment_bp)
    app.register_blueprint(procurement_plan_bp)  # 采购计划池
    app.register_blueprint(web_announcement_bp)  # 官网公告存档
    app.register_blueprint(doc_intake_attach_bp)  # 资料智能归档 → 自动挂载到业务模块
    app.register_blueprint(auth_letter_pending_bp)  # 授权函任务清单
    from routes.storage_api import bp as storage_bp
    app.register_blueprint(storage_bp)            # 对象存储直传/签名（未配 OSS 时自动降级为本地）

    # 确保所有表都已创建（新模型自动建表）
    with app.app_context():
        from models.announcement import Announcement  # noqa: F401
        from models.announcement_attachment import AnnouncementAttachment  # noqa: F401
        from models.agency_template import AgencyTemplate  # noqa: F401
        from models.auth_letter_record import AuthLetterRecord  # noqa: F401
        from models.procurement_plan import (ProcurementPlan,  # noqa: F401
                                             ProcurementPlanAttachment)
        from models.web_announcement import WebAnnouncement  # noqa: F401 官网公告存档
        from models.procurement_demand import ProcurementDemand  # noqa: F401
        from models.procurement_result import ProcurementResult  # noqa: F401
        from models.contract import Contract  # noqa: F401
        from models.contract_attachment import ContractAttachment  # noqa: F401
        from models.internal_bid_demand import InternalBidDemand  # noqa: F401
        from models.sys_config import SysConfig                   # noqa: F401
        from models.inquiry_letter import InquiryLetter           # noqa: F401
        from models.inquiry_supplier import InquirySupplier       # noqa: F401
        from models.inquiry_attachment import InquiryAttachment   # noqa: F401
        from models.inquiry_template import InquiryTemplate       # noqa: F401
        from models.inquiry_review import InquiryReview, InquirySupplierFile  # noqa: F401
        from models.message import Message                         # noqa: F401
        from models.todo import Todo                               # noqa: F401
        from models.chat_message import ChatMessage                # noqa: F401
        from models.ccgp_notice import CcgpNotice                  # noqa: F401
        from models.doc_form import DocForm                        # noqa: F401
        from models.bid_board_project import BidBoardProject      # noqa: F401
        from models.role_permission import RolePermission         # noqa: F401
        from models.procurement_doc_attachment import ProcurementDocAttachment  # noqa: F401
        from models.package import Package                         # noqa: F401
        from models.procurement_round import ProcurementRound      # noqa: F401
        from models.round_package import RoundPackage              # noqa: F401
        from models.llm_usage import LlmUsage                       # noqa: F401
        from models.agency_balance import AgencyBalance             # noqa: F401
        from models.bid_review import (                             # noqa: F401
            BidReviewTask, BidReviewCriteria, BidReviewResult, BidReviewResultItem,
            BidReviewResultFile,
        )
        from models.law import Law  # noqa: F401  法规库
        from models.supervision import SupervisionChannel  # noqa: F401  投诉质疑数据库
        from models.user_balance import UserBalance  # noqa: F401  耗子AI按人计费余额
        from models.hermes_task import HermesTask  # noqa: F401  Hermes 自动填报任务
        from models.approval_log import ApprovalLog  # noqa: F401  审批驳回过程留痕
        from models.agency_assessment import AgencyAssessment  # noqa: F401  代理机构考核
        db.create_all()

        # rd-web 常驻登录会话：起回收线程，空闲会话自动关掉释放内存。
        # 会话本身按需创建（首次推送时登录），此处只管回收。
        try:
            from services import rdweb_session as _rs
            _rs.start_reaper()
        except Exception as _e:
            print("[rdweb] 会话回收线程启动失败：", _e, flush=True)

        # SQLite 开 WAL：投标审查的后台线程需要边写边读（一写多读并发）
        from sqlalchemy import text as _text_wal
        with db.engine.connect() as _conn_wal:
            _conn_wal.execute(_text_wal("PRAGMA journal_mode=WAL"))
            _conn_wal.commit()

        # ── 连接级 PRAGMA：journal_mode 是**库级**设置（设一次就持久），但
        #    synchronous / busy_timeout 是**连接级**的，每条新连接都要重设一遍。
        #    · synchronous=NORMAL：WAL 下的标准搭配，提交不再每次 fsync，写入快很多。
        #      代价是**突然断电**可能丢最后几个事务（数据库本身不会损坏）；
        #      想要最高持久性就把下面这行改回 FULL。
        #    · busy_timeout=15s：写高峰时先等锁而不是直接抛 "database is locked"
        #      （原来只有驱动默认的 5 秒，多人同时提交容易 500）。
        from sqlalchemy import event as _sa_event

        @_sa_event.listens_for(db.engine, "connect")
        def _sqlite_conn_pragmas(dbapi_conn, _rec):      # noqa: ANN001
            cur = dbapi_conn.cursor()
            try:
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.execute("PRAGMA busy_timeout=15000")
                cur.execute("PRAGMA foreign_keys=ON")
            finally:
                cur.close()

        # ── WAL 定期检查点：WAL 文件只在检查点时回收，持续读会一直推迟它。
        #    实测涨到 9.9MB 还没回收；WAL 越大，**别的服务读 pms.db 快照看到的数据越旧**
        #    （llm-gateway 就踩过：不 checkpoint 就读到旧值）。每 10 分钟截断一次。
        def _wal_checkpoint_loop():
            import time as _t
            while True:
                _t.sleep(int(os.environ.get("WAL_CHECKPOINT_SEC") or "600"))
                try:
                    with app.app_context():
                        with db.engine.connect() as _c:
                            _c.execute(_text_wal("PRAGMA wal_checkpoint(TRUNCATE)"))
                            _c.commit()
                except Exception as _e:
                    print("[wal] 检查点失败：", _e, flush=True)

        import threading as _th_wal
        _th_wal.Thread(target=_wal_checkpoint_loop, daemon=True).start()

        # 高频过滤列加索引（幂等 IF NOT EXISTS，不改数据；加速列表/归档/权限过滤）
        _indexes = [
            "CREATE INDEX IF NOT EXISTS ix_projects_officer ON projects(officer)",
            "CREATE INDEX IF NOT EXISTS ix_projects_agency_code ON projects(agency_code)",
            "CREATE INDEX IF NOT EXISTS ix_projects_status ON projects(status)",
            "CREATE INDEX IF NOT EXISTS ix_projects_is_deleted ON projects(is_deleted)",
            "CREATE INDEX IF NOT EXISTS ix_contracts_project_id ON contracts(project_id)",
            "CREATE INDEX IF NOT EXISTS ix_procresults_project_id ON procurement_results(project_id)",
            "CREATE INDEX IF NOT EXISTS ix_announcements_project_id ON announcements(project_id)",
            "CREATE INDEX IF NOT EXISTS ix_inquiry_letters_project_id ON inquiry_letters(project_id)",
            "CREATE INDEX IF NOT EXISTS ix_authletters_project_id ON auth_letter_records(project_id)",
            "CREATE INDEX IF NOT EXISTS ix_procrounds_project_id ON procurement_rounds(project_id)",
            "CREATE INDEX IF NOT EXISTS ix_docatt_proj_kind_round ON procurement_doc_attachments(project_id, kind, round_number)",
        ]
        with db.engine.connect() as _conn_ix:
            for _stmt in _indexes:
                try:
                    _conn_ix.execute(_text_wal(_stmt))
                except Exception:
                    pass
            _conn_ix.commit()

        # 院内竞选需求(1.2)新增手填 项目名称/预算 列（去掉「关联已立项项目」）
        with db.engine.connect() as _conn_ibd:
            _cols = {r[1] for r in _conn_ibd.execute(_text_wal("PRAGMA table_info(internal_bid_demands)"))}
            if "project_name" not in _cols:
                _conn_ibd.execute(_text_wal("ALTER TABLE internal_bid_demands ADD COLUMN project_name TEXT DEFAULT ''"))
            if "budget_amount" not in _cols:
                _conn_ibd.execute(_text_wal("ALTER TABLE internal_bid_demands ADD COLUMN budget_amount REAL"))
            _conn_ibd.commit()

        # 代理机构轮派：新增 in_rotation / rotation_seq 列 + 录入「内江市政府采购中心」
        with db.engine.connect() as _conn_ag:
            _cols = {r[1] for r in _conn_ag.execute(_text_wal("PRAGMA table_info(agencies)"))}
            if "in_rotation" not in _cols:
                _conn_ag.execute(_text_wal("ALTER TABLE agencies ADD COLUMN in_rotation INTEGER DEFAULT 1"))
            if "rotation_seq" not in _cols:
                _conn_ag.execute(_text_wal("ALTER TABLE agencies ADD COLUMN rotation_seq INTEGER DEFAULT 0"))
            # 既有代理默认参与轮次；rotation_seq 为 0 的按 id 顺序回填初始顺序
            _conn_ag.execute(_text_wal("UPDATE agencies SET in_rotation=1 WHERE in_rotation IS NULL"))
            _conn_ag.execute(_text_wal(
                "UPDATE agencies SET rotation_seq=id WHERE COALESCE(rotation_seq,0)=0 AND COALESCE(in_rotation,1)=1"))
            # 内江市政府采购中心：不参与轮次（集采/医疗设备时单独指派）
            _has_zc = _conn_ag.execute(_text_wal(
                "SELECT 1 FROM agencies WHERE name='内江市政府采购中心'")).first()
            if not _has_zc:
                _conn_ag.execute(_text_wal(
                    "INSERT INTO agencies (code,name,active,in_rotation,rotation_seq) "
                    "VALUES ('ZC','内江市政府采购中心',1,0,0)"))
            # 机构基本信息列：法人/联系方式/地址/集采标记（采购部助理手工维护）
            for _c, _t in (("legal_rep", "TEXT DEFAULT ''"), ("phone", "TEXT DEFAULT ''"),
                           ("address", "TEXT DEFAULT ''"), ("is_central", "INTEGER DEFAULT 0")):
                if _c not in _cols:
                    _conn_ag.execute(_text_wal(f"ALTER TABLE agencies ADD COLUMN {_c} {_t}"))
            _conn_ag.execute(_text_wal("UPDATE agencies SET is_central=1 WHERE name='内江市政府采购中心'"))
            _conn_ag.commit()

        # 给尚无余额记录的代理机构播种初始余额（默认 100 元）
        from services.billing import seed_balances
        seed_balances()

        # 首次写入各角色默认权限（表为空时）
        from services.permission import seed_default_perms
        seed_default_perms()

        # 幂等回填：为存量库补新增权限（seed 只在空表时跑，新增权限需单独补）
        from models.role_permission import RolePermission as _RP
        for _perm in ("file-ocr", "bid-review", "inquiry-review"):
            for _role in ("assistant", "officer", "leader"):
                _has = db.session.execute(
                    db.select(_RP).filter_by(role=_role, perm_key=_perm)
                ).first()
                if not _has:
                    db.session.add(_RP(role=_role, perm_key=_perm))
        db.session.commit()

        # 预填默认邮件配置
        import datetime as _dt_cfg
        _now_cfg = _dt_cfg.datetime.now().isoformat(timespec="seconds")
        _email_defaults = {
            "email_smtp_host":    "smtp.163.com",
            "email_smtp_port":    "465",
            "email_address":      "njyycgbxjh@163.com",
            "email_auth_code":    "RHvFa38MtrkmARF5",
            "email_sender_name":  "内江市第一人民医院采购部",
        }
        for _k, _v in _email_defaults.items():
            if not db.session.get(SysConfig, _k):
                db.session.add(SysConfig(key=_k, value=_v, updated_at=_now_cfg))
        db.session.commit()

        # 为 projects 表追加新列
        from sqlalchemy import text as _text2
        with db.engine.connect() as _conn2:
            _existing2 = {row[1] for row in _conn2.execute(
                _text2("PRAGMA table_info(projects)")
            )}
            if "round" not in _existing2:
                _conn2.execute(_text2("ALTER TABLE projects ADD COLUMN round INTEGER DEFAULT 1"))
            for _col, _typedef in [
                ("demand_confirmed",    "INTEGER DEFAULT 0"),
                ("demand_confirmed_by", "TEXT DEFAULT ''"),
                ("demand_confirmed_at", "TEXT DEFAULT ''"),
                ("doc_confirmed",       "INTEGER DEFAULT 0"),
                ("doc_confirmed_by",    "TEXT DEFAULT ''"),
                ("doc_confirmed_at",    "TEXT DEFAULT ''"),
                ("doc_agency_contact",  "TEXT DEFAULT ''"),
                ("doc_agency_phone",    "TEXT DEFAULT ''"),
                ("agency_rdweb_serial_no",    "TEXT DEFAULT ''"),
                ("agency_rdweb_submitted_at", "TEXT DEFAULT ''"),
            ]:
                if _col not in _existing2:
                    _conn2.execute(_text2(
                        f"ALTER TABLE projects ADD COLUMN {_col} {_typedef}"
                    ))
            _conn2.commit()

        # 为 contracts 表追加 rd-web 合同审签流水号列
        with db.engine.connect() as _conn_ct:
            _existing_ct = {row[1] for row in _conn_ct.execute(
                _text2("PRAGMA table_info(contracts)")
            )}
            for _col, _typedef in [
                ("rdweb_serial_no",    "TEXT DEFAULT ''"),
                ("rdweb_submitted_at", "TEXT DEFAULT ''"),
            ]:
                if _col not in _existing_ct:
                    _conn_ct.execute(_text2(
                        f"ALTER TABLE contracts ADD COLUMN {_col} {_typedef}"
                    ))
            _conn_ct.commit()

        # 为 procurement_demands 表追加新列（SQLite 不支持自动迁移）
        new_cols = [
            ("survey_needed",         "TEXT DEFAULT '不需要'"),
            ("survey_industry",       "TEXT DEFAULT ''"),
            ("survey_market",         "TEXT DEFAULT ''"),
            ("survey_history",        "TEXT DEFAULT ''"),
            ("survey_followup",       "TEXT DEFAULT ''"),
            ("survey_other",          "TEXT DEFAULT ''"),
            ("sme_policy",            "TEXT DEFAULT ''"),
            ("is_eco_product",        "TEXT DEFAULT '否'"),
            ("is_energy_save",        "TEXT DEFAULT '否'"),
            ("has_import_product",    "TEXT DEFAULT '否'"),
            ("is_govt_service",       "TEXT DEFAULT '否'"),
            ("is_info_system",        "TEXT DEFAULT '否'"),
            ("is_research_equip",     "TEXT DEFAULT '否'"),
            ("pricing_method",        "TEXT DEFAULT ''"),
            ("allow_consortium",      "TEXT DEFAULT '否'"),
            ("allow_subcontract",     "TEXT DEFAULT '否'"),
            ("contract_type",         "TEXT DEFAULT ''"),
            ("contract_location",     "TEXT DEFAULT ''"),
            ("acceptance_delivery",   "TEXT DEFAULT ''"),
            ("warranty_terms",        "TEXT DEFAULT ''"),
            ("ip_terms",              "TEXT DEFAULT ''"),
            ("cost_risk_terms",       "TEXT DEFAULT ''"),
            ("other_contract_terms",  "TEXT DEFAULT ''"),
            ("performance_bond_terms","TEXT DEFAULT ''"),
            ("acceptance_org",        "TEXT DEFAULT ''"),
            ("invite_other_supplier", "TEXT DEFAULT '否'"),
            ("invite_expert",         "TEXT DEFAULT '否'"),
            ("invite_service_obj",    "TEXT DEFAULT '否'"),
            ("invite_third_party",    "TEXT DEFAULT '否'"),
            ("acceptance_misc",       "TEXT DEFAULT ''"),
            ("acceptance_extra",      "TEXT DEFAULT ''"),
        ]
        from sqlalchemy import text
        with db.engine.connect() as conn:
            existing = {row[1] for row in conn.execute(
                text("PRAGMA table_info(procurement_demands)")
            )}
            for col, typedef in new_cols:
                if col not in existing:
                    conn.execute(text(
                        f"ALTER TABLE procurement_demands ADD COLUMN {col} {typedef}"
                    ))
            conn.commit()

        # 为 procurement_doc_attachments 表追加新列
        with db.engine.connect() as conn3:
            existing3 = {row[1] for row in conn3.execute(
                text("PRAGMA table_info(procurement_doc_attachments)")
            )}
            if "sha256" not in existing3:
                conn3.execute(text(
                    "ALTER TABLE procurement_doc_attachments ADD COLUMN sha256 TEXT DEFAULT ''"
                ))
            # round_number：采购文件附件归属的轮次（第二期按轮区分文件用）
            if "round_number" not in existing3:
                conn3.execute(text(
                    "ALTER TABLE procurement_doc_attachments ADD COLUMN round_number INTEGER DEFAULT 1"
                ))
            conn3.commit()

        # 为 announcements 表追加更正公告（6.3）专用列
        with db.engine.connect() as conn6:
            existing6 = {row[1] for row in conn6.execute(
                text("PRAGMA table_info(announcements)")
            )}
            corr_cols = (
                ("corr_scope", "TEXT DEFAULT ''"),
                ("corr_reason", "TEXT DEFAULT ''"),
                ("corr_items_json", "TEXT DEFAULT '[]'"),
                ("corr_in_attachment", "INTEGER DEFAULT 0"),
                ("corr_seq", "INTEGER DEFAULT 1"),
            )
            for col, typedef in corr_cols:
                if col not in existing6:
                    conn6.execute(text(
                        f"ALTER TABLE announcements ADD COLUMN {col} {typedef}"
                    ))
            conn6.commit()

        # 为 procurement_rounds 表追加开标标记列（按轮记录能否开标 + 流标两步确认）
        with db.engine.connect() as conn5:
            existing5 = {row[1] for row in conn5.execute(
                text("PRAGMA table_info(procurement_rounds)")
            )}
            for col in ("can_open", "can_open_at", "can_open_by",
                        "can_open_status", "can_open_reason",
                        "can_open_confirmed_by", "can_open_confirmed_at"):
                if col not in existing5:
                    conn5.execute(text(
                        f"ALTER TABLE procurement_rounds ADD COLUMN {col} TEXT DEFAULT ''"
                    ))
            # 历史已标记的轮次（can_open 有值但状态空）视为「已确认」，避免被当成待确认
            conn5.execute(text(
                "UPDATE procurement_rounds SET can_open_status='已确认' "
                "WHERE can_open != '' AND (can_open_status IS NULL OR can_open_status='')"
            ))
            conn5.commit()

        # 为 inquiry_letters 表追加新列（询/议价邀请函公告体例字段）
        with db.engine.connect() as conn4:
            existing4 = {row[1] for row in conn4.execute(
                text("PRAGMA table_info(inquiry_letters)")
            )}
            for col in ("detail", "requirements"):
                if col not in existing4:
                    conn4.execute(text(
                        f"ALTER TABLE inquiry_letters ADD COLUMN {col} TEXT DEFAULT ''"
                    ))
            # 轮次覆盖列（同轮询价废标转议价）
            if "round_no" not in existing4:
                conn4.execute(text(
                    "ALTER TABLE inquiry_letters ADD COLUMN round_no INTEGER"
                ))
            conn4.commit()

        # 为 inquiry_suppliers 表追加评审字段（模块8 询议价评审）
        with db.engine.connect() as conn4s:
            existing4s = {row[1] for row in conn4s.execute(
                text("PRAGMA table_info(inquiry_suppliers)")
            )}
            for col in ("qual_pass", "conform_pass", "final_price",
                        "review_rank", "fail_reason"):
                if col not in existing4s:
                    conn4s.execute(text(
                        f"ALTER TABLE inquiry_suppliers ADD COLUMN {col} TEXT DEFAULT ''"
                    ))
            if "responded" not in existing4s:
                conn4s.execute(text(
                    "ALTER TABLE inquiry_suppliers ADD COLUMN responded INTEGER DEFAULT 0"
                ))
                # 一次性回填：已填过评审数据的供应商视为已递交响应
                conn4s.execute(text(
                    "UPDATE inquiry_suppliers SET responded=1 "
                    "WHERE quote_amount IS NOT NULL OR qual_pass<>'' "
                    "   OR conform_pass<>'' OR final_price<>''"
                ))
            conn4s.commit()

        # 为 inquiry_reviews 表追加「提前开启评审」字段
        with db.engine.connect() as conn_ir:
            existing_ir = {row[1] for row in conn_ir.execute(
                text("PRAGMA table_info(inquiry_reviews)")
            )}
            if "early_open" not in existing_ir:
                conn_ir.execute(text(
                    "ALTER TABLE inquiry_reviews ADD COLUMN early_open INTEGER DEFAULT 0"))
            for col in ("early_open_by", "early_open_at"):
                if col not in existing_ir:
                    conn_ir.execute(text(
                        f"ALTER TABLE inquiry_reviews ADD COLUMN {col} TEXT DEFAULT ''"))
            conn_ir.commit()

        # 为 todos 表追加系统派单字段（source / source_key）
        with db.engine.connect() as conn_td:
            existing_td = {row[1] for row in conn_td.execute(
                text("PRAGMA table_info(todos)")
            )}
            if "source" not in existing_td:
                conn_td.execute(text(
                    "ALTER TABLE todos ADD COLUMN source TEXT DEFAULT 'manual'"))
            if "source_key" not in existing_td:
                conn_td.execute(text(
                    "ALTER TABLE todos ADD COLUMN source_key TEXT DEFAULT ''"))
            conn_td.commit()

        # 为投标审查四表追加新列（六类条目抽取 + 评分/比价重构）
        _br_cols = {
            "bid_review_tasks": [
                ("progress",        "TEXT DEFAULT ''"),
                ("eval_method",     "TEXT DEFAULT ''"),
                ("price_score_max", "TEXT DEFAULT ''"),
                ("price_formula",   "TEXT DEFAULT ''"),
                ("lots_json",       "TEXT DEFAULT '[]'"),
                ("summary_json",    "TEXT DEFAULT '[]'"),
            ],
            "bid_review_criteria": [
                ("category",   "TEXT DEFAULT '资格'"),
                ("lot_no",     "TEXT DEFAULT '通用'"),
                ("max_score",  "REAL"),
                ("score_rule", "TEXT DEFAULT ''"),
            ],
            "bid_review_results": [
                ("lot_no",          "TEXT DEFAULT '通用'"),
                ("bid_price",       "TEXT DEFAULT ''"),
                ("price_page",      "TEXT DEFAULT ''"),
                ("price_edited_by", "TEXT DEFAULT ''"),
            ],
            "bid_review_result_items": [
                ("ai_score",    "REAL"),
                ("ai_reason",   "TEXT DEFAULT ''"),
                ("final_score", "REAL"),
            ],
        }
        with db.engine.connect() as conn7:
            for _tbl, _cols in _br_cols.items():
                existing7 = {row[1] for row in conn7.execute(
                    text(f"PRAGMA table_info({_tbl})")
                )}
                for col, typedef in _cols:
                    if col not in existing7:
                        conn7.execute(text(
                            f"ALTER TABLE {_tbl} ADD COLUMN {col} {typedef}"
                        ))
            conn7.commit()

        # ── 审批驳回 / 不确认：各单据追加驳回字段（approval_logs 表由 create_all 建）──
        _rej_cols = {
            "announcements": [
                ("survey_content",       "TEXT DEFAULT ''"),
                ("survey_qualification", "TEXT DEFAULT ''"),
                ("survey_quote_req",     "TEXT DEFAULT ''"),
                ("survey_materials",     "TEXT DEFAULT ''"),
                ("survey_deadline",      "TEXT DEFAULT ''"),
                ("survey_submit_way",    "TEXT DEFAULT ''"),
                ("survey_note",          "TEXT DEFAULT ''"),
                ("ss_goods_desc",        "TEXT DEFAULT ''"),
                ("ss_reason",            "TEXT DEFAULT ''"),
                ("ss_supplier_name",     "TEXT DEFAULT ''"),
                ("ss_supplier_addr",     "TEXT DEFAULT ''"),
                ("ss_experts_json",      "TEXT DEFAULT '[]'"),
                ("ss_publicity_start",   "TEXT DEFAULT ''"),
                ("ss_publicity_end",     "TEXT DEFAULT ''"),
                ("ss_objection_dept",    "TEXT DEFAULT ''"),
                ("ss_objection_contact", "TEXT DEFAULT ''"),
                ("ss_objection_phone",   "TEXT DEFAULT ''"),
                ("ss_objection_addr",    "TEXT DEFAULT ''"),
                ("reject_reason", "TEXT DEFAULT ''"),
                ("reject_count",  "INTEGER DEFAULT 0"),
                ("rejected_by",   "TEXT DEFAULT ''"),
                ("rejected_at",   "TEXT DEFAULT ''"),
            ],
            "procurement_rounds": [
                ("demand_reject_reason", "TEXT DEFAULT ''"),
                ("demand_reject_count",  "INTEGER DEFAULT 0"),
                ("demand_rejected_by",   "TEXT DEFAULT ''"),
                ("demand_rejected_at",   "TEXT DEFAULT ''"),
                ("doc_reject_reason",    "TEXT DEFAULT ''"),
                ("doc_reject_count",     "INTEGER DEFAULT 0"),
                ("doc_rejected_by",      "TEXT DEFAULT ''"),
                ("doc_rejected_at",      "TEXT DEFAULT ''"),
                ("review_status",        "TEXT DEFAULT ''"),
                ("review_confirmed_by",  "TEXT DEFAULT ''"),
                ("review_confirmed_at",  "TEXT DEFAULT ''"),
                ("review_reject_reason", "TEXT DEFAULT ''"),
                ("review_reject_count",  "INTEGER DEFAULT 0"),
                ("review_rejected_by",   "TEXT DEFAULT ''"),
                ("review_rejected_at",   "TEXT DEFAULT ''"),
            ],
            "procurement_results": [
                ("reject_reason",      "TEXT DEFAULT ''"),
                ("reject_count",       "INTEGER DEFAULT 0"),
                ("rejected_by",        "TEXT DEFAULT ''"),
                ("rejected_at",        "TEXT DEFAULT ''"),
                ("not_confirm_reason", "TEXT DEFAULT ''"),
                ("not_confirm_count",  "INTEGER DEFAULT 0"),
                ("not_confirmed_by",   "TEXT DEFAULT ''"),
                ("not_confirmed_at",   "TEXT DEFAULT ''"),
                ("recheck_handling",   "TEXT DEFAULT ''"),
                ("recheck_note",       "TEXT DEFAULT ''"),
                ("recheck_by",         "TEXT DEFAULT ''"),
                ("recheck_at",         "TEXT DEFAULT ''"),
            ],
            "contracts": [
                ("reject_reason", "TEXT DEFAULT ''"),
                ("reject_count",  "INTEGER DEFAULT 0"),
                ("rejected_by",   "TEXT DEFAULT ''"),
                ("rejected_at",   "TEXT DEFAULT ''"),
            ],
        }
        with db.engine.connect() as conn8:
            for _tbl, _cols in _rej_cols.items():
                existing8 = {row[1] for row in conn8.execute(
                    text(f"PRAGMA table_info({_tbl})")
                )}
                if not existing8:
                    continue          # 表还没建（首次启动），create_all 已带上新列
                for col, typedef in _cols:
                    if col not in existing8:
                        conn8.execute(text(
                            f"ALTER TABLE {_tbl} ADD COLUMN {col} {typedef}"
                        ))
            conn8.commit()

        # ── 一次性回填：为存量项目补出「采购轮次 / 包」骨架（幂等）──────
        from models.project import Project as _BFProj
        from models.package import Package as _BFPkg
        from models.procurement_round import ProcurementRound as _BFRound
        from models.round_package import RoundPackage as _BFRP
        from models.procurement_result import ProcurementResult as _BFRes
        import datetime as _dt_bf
        import json as _json_bf

        _now_bf = _dt_bf.datetime.now().isoformat(timespec="seconds")
        # 询/议价、紧急采购是**独立轨道，本就不走轮次系统**（真相在 inquiry_letters/
        # inquiry_reviews，见 services/project_progress.py 的注释）。给它们补轮次会造成
        # current_round=1 → 「7. 询/议价函」的可立函下拉把项目排除掉（条件是"无轮次或已废标"）
        # → 经办人立了项却建不了询价函、管理页里什么都看不到。2026-08-04 实测踩中。
        _NO_ROUND_METHODS = ("院内询价", "院内议价", "医用耗材紧急采购")
        for _p in db.session.execute(db.select(_BFProj)).scalars().all():
            if _p.is_draft:
                continue  # 草稿项目不建轮次
            if (_p.method or "") in _NO_ROUND_METHODS:
                continue  # 独立轨道，不建轮次
            # 已有轮次则跳过
            if db.session.execute(
                db.select(_BFRound).filter_by(project_id=_p.id)
            ).first():
                continue
            # 包数量：取历史采购结果里最大的包数，没有则按 1 个包
            _maxpk = 1
            for _r in db.session.execute(
                db.select(_BFRes).filter_by(project_id=_p.id)
            ).scalars().all():
                try:
                    _maxpk = max(_maxpk, len(_json_bf.loads(_r.packages_json or "[]")))
                except Exception:
                    pass
            _pkgs = []
            for _i in range(1, _maxpk + 1):
                _pk = _BFPkg(project_id=_p.id, package_no=_i, status="进行中", created_at=_now_bf)
                db.session.add(_pk)
                _pkgs.append(_pk)
            db.session.flush()
            _round1 = _BFRound(
                project_id=_p.id, round_number=1,
                demand_confirmed=_p.demand_confirmed or 0,
                demand_confirmed_by=_p.demand_confirmed_by or "",
                demand_confirmed_at=_p.demand_confirmed_at or "",
                doc_confirmed=_p.doc_confirmed or 0,
                doc_confirmed_by=_p.doc_confirmed_by or "",
                doc_confirmed_at=_p.doc_confirmed_at or "",
                doc_agency_contact=getattr(_p, "doc_agency_contact", "") or "",
                doc_agency_phone=getattr(_p, "doc_agency_phone", "") or "",
                status="进行中", created_at=_now_bf,
            )
            db.session.add(_round1)
            db.session.flush()
            for _pk in _pkgs:
                db.session.add(_BFRP(round_id=_round1.id, package_id=_pk.id, result="待定"))
        db.session.commit()

        # ── 一次性回填：把项目当前的开标标记 can_open 落到其最新轮次（幂等）──
        for _p in db.session.execute(db.select(_BFProj)).scalars().all():
            if not (_p.can_open or "").strip():
                continue
            _latest = db.session.execute(
                db.select(_BFRound).filter_by(project_id=_p.id)
                .order_by(_BFRound.round_number.desc())
            ).scalars().first()
            # 轮次已有标记则跳过；时间/操作人历史不可考，留空
            if _latest and not (_latest.can_open or "").strip():
                _latest.can_open = _p.can_open
        db.session.commit()

    # 提供前端静态资源（生产模式）
    @app.route("/assets/<path:filename>")
    def assets(filename):
        resp = send_from_directory(os.path.join(dist_path, "assets"), filename)
        # Vite 构建的 asset 文件名含内容 hash，内容不变文件名也不变，可永久缓存
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def index(path):
        # API 路由已被蓝图优先匹配，这里只处理前端路由。
        # 未命中的 /api/* 不应回退到 index.html（否则前端 fetch 会拿到 200+HTML，
        # 误以为是文件内容），统一返回 404 JSON 便于排查。
        if path.startswith("api/"):
            return jsonify({"ok": False, "error": "接口不存在"}), 404
        # 根级真实静态文件（favicon、pms-icon.svg 等）直接返回；
        # 其余路径交给前端路由（SPA），统一回 index.html。
        if path:
            candidate = os.path.join(dist_path, path)
            if os.path.isfile(candidate) and os.path.commonpath(
                [os.path.realpath(candidate), os.path.realpath(dist_path)]
            ) == os.path.realpath(dist_path):
                return send_from_directory(dist_path, path)
        resp = send_from_directory(dist_path, "index.html")
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    # ── 滑块验证同源反代（→ captcha-svc 3060），供登录页调用验证接口/加载 widget ──
    import requests as _rq
    _CAPTCHA_URL = os.environ.get("CAPTCHA_URL", "http://127.0.0.1:3060")

    @app.route("/captcha/<path:sub>", methods=["GET", "POST"])
    def _captcha_proxy(sub):
        from flask import request as _req, Response
        url = f"{_CAPTCHA_URL}/captcha/{sub}"
        try:
            if _req.method == "POST":
                r = _rq.post(url, data=_req.get_data(),
                             headers={"Content-Type": _req.headers.get("Content-Type", "application/json")},
                             timeout=10)
            else:
                r = _rq.get(url, params=_req.args, timeout=10)
            return Response(r.content, status=r.status_code,
                            mimetype=r.headers.get("Content-Type", "application/json"))
        except Exception as e:
            return jsonify(ok=False, error=str(e)[:120]), 502

    # ── 资料智能归档 同源反代（→ doc-intake 9080），供 PMS 工具栏 iframe 内嵌 ──
    _INTAKE_URL = os.environ.get("DOC_INTAKE_URL", "http://127.0.0.1:9080")

    # ── 反代用：把 request.stream 包成 requests 能算长度的对象 ───────────
    # 直接把 stream 交给 requests，它算不出长度就会自作主张加
    # Transfer-Encoding: chunked；若同时又转发了 Content-Length，
    # 两个头并存 → 对端（gunicorn/express）判为非法请求头直接 400。
    # 给包装对象一个 .len，requests 就只发 Content-Length。
    class _StreamBody:
        def __init__(self, stream, length):
            self._s = stream
            self.len = length

        def read(self, n=-1):
            return self._s.read() if n is None or n < 0 else self._s.read(n)

    def _fwd_body(_req):
        """返回 (body, extra_headers)：知道长度就按长度发，不知道就退分块编码。"""
        try:
            cl = int(_req.headers.get("Content-Length") or 0)
        except ValueError:
            cl = 0
        if cl > 0:
            return _StreamBody(_req.stream, cl), {}
        return _req.stream, {}

    @app.route("/doc-intake-svc/", defaults={"sub": ""}, methods=["GET", "POST"])
    @app.route("/doc-intake-svc/<path:sub>", methods=["GET", "POST"])
    def _intake_proxy(sub):
        from flask import request as _req, Response, stream_with_context
        url = f"{_INTAKE_URL}/{sub}"
        try:
            if _req.method == "POST":
                # 流式转发：get_data() 会把整个上传体读进 PMS 进程内存
                # （291MB 的件在这里要占两三份），大文件必须边收边转。
                hdr = {"Content-Type": _req.headers.get("Content-Type", "application/octet-stream")}
                body, extra = _fwd_body(_req)
                hdr.update(extra)
                r = _rq.post(url, data=body, params=_req.args,
                             headers=hdr, timeout=650, stream=True)
            else:
                r = _rq.get(url, params=_req.args, timeout=60, stream=True)
            return Response(stream_with_context(r.iter_content(chunk_size=64 * 1024)),
                            status=r.status_code,
                            mimetype=r.headers.get("Content-Type", "text/html"))
        except Exception as e:
            return jsonify(ok=False, error=str(e)[:160]), 502

    # ── 牛马 agent 同源反代（→ 各人自己的 officer-agent 盒子，流式 SSE）──
    # 一人一盒（B 方案物理隔离）：按登录人路由到各自端口，盒子之间互不可见。
    # 新增经办人 = 起一个容器 + 这里加一行映射。
    _OFFICER_BOXES = {
        "黄新博": os.environ.get("OFFICER_URL_HXB", "http://127.0.0.1:3071"),
        "郑跃俊": os.environ.get("OFFICER_URL_ZYJ", "http://127.0.0.1:3072"),
    }
    # 与 agent 盒子约定的共享密钥：PMS 这头已校验登录态，凭密钥把「谁在用」传过去。
    # 盒子只监听 127.0.0.1，加上这道密钥，绕过 PMS 直接打 agent 端口就不成立了。
    def _proxy_secret():
        p = os.environ.get("OFFICER_PROXY_SECRET_FILE", "/home/huangxb/pms/.officer_proxy_secret")
        try:
            with open(p, encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return os.environ.get("OFFICER_PROXY_SECRET", "")

    @app.route("/officer-agent/", defaults={"sub": ""}, methods=["GET", "POST", "DELETE"])
    @app.route("/officer-agent/<path:sub>", methods=["GET", "POST", "DELETE"])
    def _officer_proxy(sub):
        from flask import request as _req, Response, session, stream_with_context
        user = session.get("user")
        target = _OFFICER_BOXES.get(user or "")
        if not target:                            # 没盒子的账号一律不给
            return jsonify(ok=False, error="牛马助手未对当前账号开放"), 403
        url = f"{target}/{sub}"
        from urllib.parse import quote as _q
        # HTTP 头只能 ASCII，中文用户名必须编码后再传（否则到对面变乱码）
        hdr = {"X-Proxy-Secret": _proxy_secret(), "X-Proxy-User": _q(user)}
        try:
            if _req.method == "POST":
                hdr["Content-Type"] = _req.headers.get("Content-Type", "application/json")
                # 流式转发，拖进牛马面板的大文件不再整份占 PMS 内存
                body, extra = _fwd_body(_req)
                hdr.update(extra)
                r = _rq.post(url, data=body, params=_req.args, headers=hdr,
                             stream=True, timeout=300)
            elif _req.method == "DELETE":
                r = _rq.delete(url, params=_req.args, headers=hdr, stream=True, timeout=60)
            else:
                r = _rq.get(url, params=_req.args, headers=hdr, stream=True, timeout=120)
            return Response(stream_with_context(r.iter_content(chunk_size=None)),
                            status=r.status_code,
                            mimetype=r.headers.get("Content-Type", "text/html"))
        except Exception as e:
            return jsonify(ok=False, error=str(e)[:160]), 502

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PMS_PORT", "1573"))
    print(f"[*] 采购管理系统启动: http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
