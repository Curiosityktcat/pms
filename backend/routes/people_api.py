import os, time
from flask import Blueprint, request, jsonify, send_file
from models import db
from models.people import People
from routes.utils import login_required

bp = Blueprint('people', __name__, url_prefix='/api/people')

HERE = os.path.dirname(os.path.abspath(__file__))
PMS_ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
UPLOAD_DIR = os.path.join(PMS_ROOT, '身份证', '上传')
ALLOWED_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}


def _save_photo(file, person_name: str) -> str:
    """保存上传的照片，返回相对路径（相对 PMS_ROOT）"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename)[1].lower() or '.jpg'
    if ext not in ALLOWED_EXT:
        raise ValueError('只支持 jpg/png/gif 格式')
    # 用姓名+时间戳命名，避免冲突
    filename = f"{person_name}_{int(time.time())}{ext}"
    save_path = os.path.join(UPLOAD_DIR, filename)
    file.save(save_path)
    return f'身份证/上传/{filename}'


@bp.route('', methods=['GET'])
@login_required
def list_people():
    role_type = request.args.get('role_type')
    stmt = db.select(People).filter_by(active=1)
    if role_type:
        stmt = stmt.filter_by(role_type=role_type)
    stmt = stmt.order_by(People.name)
    rows = db.session.execute(stmt).scalars().all()
    return jsonify({'ok': True, 'data': [r.to_dict() for r in rows]})


@bp.route('', methods=['POST'])
@login_required
def create_person():
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'ok': False, 'error': '姓名不能为空'}), 400

    id_card = request.form.get('id_card', '').strip()
    department = request.form.get('department', '').strip()
    role_type = request.form.get('role_type', 'representative')

    # 检查同名（警告，不阻止）
    same_name = db.session.execute(
        db.select(People).filter_by(name=name, active=1)
    ).scalars().all()
    warning = f'已存在 {len(same_name)} 位同名人员，请确认科室或身份证号不同' if same_name else None

    # 处理照片
    photo_path = ''
    if 'photo' in request.files:
        f = request.files['photo']
        if f and f.filename:
            try:
                photo_path = _save_photo(f, name)
            except ValueError as e:
                return jsonify({'ok': False, 'error': str(e)}), 400

    p = People(
        name=name, id_card=id_card, department=department,
        role_type=role_type, photo=photo_path, active=1,
    )
    db.session.add(p)
    db.session.commit()
    result = p.to_dict()
    result['warning'] = warning
    return jsonify({'ok': True, 'data': result, 'warning': warning}), 201


@bp.route('/<int:pid>', methods=['PUT'])
@login_required
def update_person(pid):
    p = db.session.get(People, pid)
    if not p:
        return jsonify({'ok': False, 'error': '人员不存在'}), 404

    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'ok': False, 'error': '姓名不能为空'}), 400

    p.name = name
    p.id_card = request.form.get('id_card', p.id_card or '').strip()
    p.department = request.form.get('department', p.department or '').strip()
    if 'role_type' in request.form:
        p.role_type = request.form['role_type']

    if 'photo' in request.files:
        f = request.files['photo']
        if f and f.filename:
            try:
                p.photo = _save_photo(f, name)
            except ValueError as e:
                return jsonify({'ok': False, 'error': str(e)}), 400

    db.session.commit()
    return jsonify({'ok': True, 'data': p.to_dict()})


@bp.route('/<int:pid>', methods=['DELETE'])
@login_required
def delete_person(pid):
    p = db.session.get(People, pid)
    if not p:
        return jsonify({'ok': False, 'error': '人员不存在'}), 404
    p.active = 0
    db.session.commit()
    return jsonify({'ok': True, 'message': '已停用'})


@bp.route('/photo/<path:photo_path>')
@login_required
def serve_photo(photo_path):
    """受保护的身份证照片服务"""
    full_path = os.path.join(PMS_ROOT, photo_path)
    if not os.path.exists(full_path):
        return jsonify({'error': '文件不存在'}), 404
    return send_file(full_path)
