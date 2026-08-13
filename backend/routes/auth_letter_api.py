import os
from flask import Blueprint, request, session, jsonify, send_file, after_this_request
from models import db
from models.project import Project
from models.agency import Agency
from models.people import People
from services import auth_letter as svc
from services.project_progress import stage_map
from routes.utils import login_required


def _current_round(pid):
    """项目当前在第几轮采购——与「待出具授权函」待办用的是同一个来源。

    授权函记错轮次的代价是待办永远消不掉（待办按 r{n} 建，授权函按 r1 存就对不上），
    所以客户端没明确给轮次时一律以服务端为准，别默认第 1 轮。
    """
    return (stage_map([pid]).get(pid, {}) or {}).get('current_round') or 1

bp = Blueprint('auth_letter', __name__, url_prefix='/api/projects')


@bp.route('/<int:pid>/auth-letter', methods=['POST'])
@login_required
def generate_auth_letter(pid):
    # 1. 取项目
    project = db.session.get(Project, pid)
    if not project:
        return jsonify({'ok': False, 'error': '项目不存在'}), 404
    if project.is_draft:
        return jsonify({'ok': False, 'error': '草稿项目无法生成授权函'}), 400
    if not project.agency_code:
        return jsonify({'ok': False, 'error': '该项目不走代理机构，无需生成授权函'}), 400

    data = request.get_json(force=True) or {}
    supervisor_id = data.get('supervisor_id')
    representative_ids = data.get('representative_ids') or []
    # 客户端不给（或给 0）就用服务端算的当前轮次；给了则尊重（补开历史轮次的授权函）
    round_number = int(data.get('round_number') or 0) or _current_round(pid)
    round_number = max(1, round_number)
    bid_time_override = (data.get('bid_time_override') or '').strip()

    if not supervisor_id or not representative_ids:
        return jsonify({'ok': False, 'error': '请选择监督人员和至少一位采购人代表'}), 400

    # 2. 取人员
    supervisor = db.session.get(People, supervisor_id)
    if not supervisor:
        return jsonify({'ok': False, 'error': '监督人员不存在'}), 404

    representatives = []
    for rid in representative_ids:
        rep = db.session.get(People, rid)
        if not rep:
            return jsonify({'ok': False, 'error': f'采购人代表(id={rid})不存在'}), 404
        representatives.append(rep)

    # 3. 取代理机构名称
    agency_name = ''
    if project.agency_code:
        a = db.session.execute(db.select(Agency).filter_by(code=project.agency_code)).scalar_one_or_none()
        agency_name = a.name if a else project.agency_code

    # 4. 生成 Word
    try:
        tmp_path = svc.generate(
            project, supervisor, representatives, agency_name,
            round_number=round_number,
            bid_time_override=bid_time_override,
        )
    except Exception as e:
        return jsonify({'ok': False, 'error': f'生成失败：{str(e)}'}), 500

    # 5. 返回文件，发送后删除临时文件
    download_name = f'授权函_{project.number or project.name}.docx'

    @after_this_request
    def cleanup(response):
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return response

    return send_file(
        tmp_path,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        as_attachment=True,
        download_name=download_name,
    )
