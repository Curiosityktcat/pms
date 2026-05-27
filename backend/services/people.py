from models import db
from models.people import People


def list_people(role_type=None):
    stmt = db.select(People).filter_by(active=1)
    if role_type:
        stmt = stmt.filter_by(role_type=role_type)
    stmt = stmt.order_by(People.name)
    return db.session.execute(stmt).scalars().all()


def get_person(pid):
    p = db.session.get(People, pid)
    if not p:
        raise ValueError('人员不存在')
    return p
