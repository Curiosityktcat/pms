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

    app.register_blueprint(auth_bp)
    app.register_blueprint(project_bp)
    app.register_blueprint(bid_bp)
    app.register_blueprint(people_bp)
    app.register_blueprint(auth_letter_bp)
    app.register_blueprint(announcement_bp)
    app.register_blueprint(agency_template_bp)

    # 确保所有表都已创建（新模型自动建表）
    with app.app_context():
        from models.announcement import Announcement  # noqa: F401
        from models.agency_template import AgencyTemplate  # noqa: F401
        db.create_all()

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
