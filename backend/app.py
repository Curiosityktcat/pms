import os
from flask import Flask, send_from_directory
from flask_cors import CORS
from models import db


def create_app():
    app = Flask(__name__)

    here = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.abspath(os.path.join(here, "..", "pms.db"))
    dist_path = os.path.abspath(os.path.join(here, "..", "frontend", "dist"))

    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "change-this-secret-key-please"

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
    from routes.bid_board_api import bp as bid_board_bp
    from routes.permission_api import bp as permission_bp
    from routes.agency_agreement_api import bp as agency_agreement_bp
    from routes.procurement_doc_api import bp as procurement_doc_bp
    from routes.template_api import bp as template_bp
    from routes.archive_api import bp as archive_bp

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
    app.register_blueprint(bid_board_bp)
    app.register_blueprint(permission_bp)
    app.register_blueprint(agency_agreement_bp)
    app.register_blueprint(procurement_doc_bp)
    app.register_blueprint(template_bp)
    app.register_blueprint(archive_bp)

    # 确保所有表都已创建（新模型自动建表）
    with app.app_context():
        from models.announcement import Announcement  # noqa: F401
        from models.announcement_attachment import AnnouncementAttachment  # noqa: F401
        from models.agency_template import AgencyTemplate  # noqa: F401
        from models.auth_letter_record import AuthLetterRecord  # noqa: F401
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
        from models.bid_board_project import BidBoardProject      # noqa: F401
        from models.role_permission import RolePermission         # noqa: F401
        from models.procurement_doc_attachment import ProcurementDocAttachment  # noqa: F401
        db.create_all()

        # 首次写入各角色默认权限（表为空时）
        from services.permission import seed_default_perms
        seed_default_perms()

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
            ]:
                if _col not in _existing2:
                    _conn2.execute(_text2(
                        f"ALTER TABLE projects ADD COLUMN {_col} {_typedef}"
                    ))
            _conn2.commit()

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
            conn3.commit()

    # 提供前端静态资源（生产模式）
    @app.route("/assets/<path:filename>")
    def assets(filename):
        return send_from_directory(os.path.join(dist_path, "assets"), filename)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def index(path):
        # API 路由已被蓝图优先匹配，这里只处理前端路由
        return send_from_directory(dist_path, "index.html")

    return app


if __name__ == "__main__":
    app = create_app()
    print("[*] 采购管理系统启动: http://0.0.0.0:1573")
    app.run(host="0.0.0.0", port=1573, debug=False)
