"""
一次性脚本：
1. 给5位监督人填入身份证号 + 照片路径
2. 把身份证目录下的照片批量导入为采购人代表
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from models import db
from models.people import People

IDCARD_DIR = os.path.join(os.path.dirname(__file__), '..', '身份证')

# 监督人已知信息（从身份证信息.txt整理）
SUPERVISORS = {
    '刘堇羽': ('511002198908026420', '刘堇羽.jpg'),
    '王勇':   ('511002197008190618', '王勇.png'),
    '余兰':   ('511002197308140321', '余兰.png'),
    '黄河':   ('513901198705220236', '黄河.jpg'),
    '钟佩廷': ('511002199403270625', '钟佩廷.png'),
}

# 主目录额外的代表（不在不常用里）
MAIN_REPS = {
    '师芮':   ('51100219950826036x', '师芮 51100219950826036x.jpg'),
    '曾旌城': ('511002198202140336', '曾旌城.png'),
    '黄新博': ('511002199604210012', '黄新博 511002199604210012.jpg'),
    '郑跃俊': ('511028199403292916', '郑跃俊.jpg'),
}


def extract_name_idcard(filename):
    """从文件名提取姓名和身份证号（如 '黄新博 511002199604210012.jpg'）"""
    base = os.path.splitext(filename)[0]
    # 身份证号：15或18位数字，末位可能是x/X
    m = re.search(r'(\d{15}(\d{2}[\dxX])?)', base)
    if m:
        idcard = m.group(1)
        name = base.replace(idcard, '').strip()
        # 去掉名字后面可能的下划线、空格等
        name = re.sub(r'[\s_\-]+$', '', name)
        return name, idcard
    return base.strip(), ''


app = create_app()
with app.app_context():
    # 1. 更新监督人信息
    for name, (idcard, photo_file) in SUPERVISORS.items():
        person = db.session.execute(
            db.select(People).filter_by(name=name)
        ).scalar_one_or_none()
        if person:
            person.id_card = idcard
            # 检查文件是否存在
            photo_path = f'身份证/{photo_file}'
            if os.path.exists(os.path.join(IDCARD_DIR, photo_file)):
                person.photo = photo_path
            print(f'[更新监督人] {name} | {idcard} | {photo_path}')
        else:
            print(f'[未找到] 监督人 {name}，跳过')

    # 2. 导入主目录的代表（已知信息）
    for name, (idcard, photo_file) in MAIN_REPS.items():
        exists = db.session.execute(
            db.select(People).filter_by(name=name, role_type='representative')
        ).scalar_one_or_none()
        if exists:
            exists.id_card = idcard
            exists.photo = f'身份证/{photo_file}'
            print(f'[更新代表] {name}')
        else:
            photo_path = f'身份证/{photo_file}'
            p = People(name=name, id_card=idcard, photo=photo_path, role_type='representative', active=1)
            db.session.add(p)
            print(f'[新增代表] {name} | {idcard}')

    # 3. 批量导入不常用目录
    buchangyong = os.path.join(IDCARD_DIR, '不常用')
    if os.path.exists(buchangyong):
        for fname in sorted(os.listdir(buchangyong)):
            if not fname.lower().endswith(('.jpg', '.jpeg', '.png', '.pdf')):
                continue
            name, idcard = extract_name_idcard(fname)
            if not name:
                continue
            exists = db.session.execute(
                db.select(People).filter_by(name=name, role_type='representative')
            ).scalar_one_or_none()
            if exists:
                if idcard and not exists.id_card:
                    exists.id_card = idcard
                continue
            photo_path = f'身份证/不常用/{fname}'
            p = People(name=name, id_card=idcard, photo=photo_path, role_type='representative', active=1)
            db.session.add(p)
            print(f'[新增代表(不常用)] {name} | {idcard or "无证号"}')

    db.session.commit()
    print('\n=== 完成 ===')

    # 打印统计
    sups = db.session.execute(db.select(People).filter_by(role_type='supervisor')).scalars().all()
    reps = db.session.execute(db.select(People).filter_by(role_type='representative')).scalars().all()
    print(f'监督人: {len(sups)}  代表: {len(reps)}')
