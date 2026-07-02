import os,sys,datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); os.chdir(os.path.dirname(os.path.abspath(__file__)))
import app as appmod
from models import db
ap=appmod.create_app()
with ap.app_context():
    from services.rdweb_scraper import import_pending
    from models.sys_config import SysConfig
    try: res=import_pending(); msg=f"定时抓取 {res}"
    except Exception as e: msg=f"定时抓取出错: {e}"
    now=datetime.datetime.now().isoformat(timespec="seconds")
    row=db.session.get(SysConfig,"rdweb_last_scrape_at")
    if row is None: db.session.add(SysConfig(key="rdweb_last_scrape_at",value=now,updated_at=now))
    else: row.value=now; row.updated_at=now
    db.session.commit()
    print(f"[{now}] {msg}")
