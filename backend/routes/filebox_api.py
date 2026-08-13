"""私人文件库 API（SFTP 式目录浏览）：仅 黄新博 一人可用。

根目录固定为 /home/huangxb/files（PMS_FILEBOX_ROOT 可覆盖）——故意不设在家目录，
避免把 ~/.ssh 私钥、pms.db、凭证等暴露到公网。支持：浏览目录、上传、下载、
新建文件夹、删除（文件/文件夹）。所有路径严格限制在根目录内（防穿越）。
"""
import datetime
import os
import shutil

from flask import Blueprint, request, session, jsonify, send_file

from routes.utils import login_required

bp = Blueprint("filebox", __name__, url_prefix="/api/filebox")

OWNER = "黄新博"   # 唯一可用账号（users.username）

FILEBOX_ROOT = os.path.abspath(
    os.environ.get("PMS_FILEBOX_ROOT", "/home/huangxb/files")
)
os.makedirs(FILEBOX_ROOT, exist_ok=True)


@bp.before_request
def _guard():
    if request.method == "OPTIONS":
        return None
    if "user" not in session:
        # 诊断：401 时记录 Cookie 是否到达（区分「key 失配」vs「Cookie 根本没带」）
        import sys
        ck = request.headers.get("Cookie", "")
        print(f"[filebox] 401 {request.method} {request.path} "
              f"has_cookie={'session' in ck} cookie_len={len(ck)} "
              f"clen={request.content_length or 0} ct={request.headers.get('Content-Type','')[:40]}",
              file=sys.stderr, flush=True)
        return jsonify({"ok": False, "error": "未登录"}), 401
    if session.get("user") != OWNER:
        return jsonify({"ok": False, "error": "无权限：私人文件库仅限本人使用"}), 403
    return None


def _resolve(relpath):
    """把相对路径解析为根目录内的绝对路径；越界/非法返回 None。"""
    relpath = (relpath or "").strip().lstrip("/")
    path = os.path.abspath(os.path.join(FILEBOX_ROOT, relpath))
    if path != FILEBOX_ROOT and os.path.commonpath([path, FILEBOX_ROOT]) != FILEBOX_ROOT:
        return None
    return path


def _relname(path):
    """根目录内绝对路径 → 相对根的路径（根本身返回空串）。"""
    rel = os.path.relpath(path, FILEBOX_ROOT)
    return "" if rel == "." else rel


@bp.route("/list", methods=["GET"])
@login_required
def list_dir():
    d = _resolve(request.args.get("path", ""))
    if not d or not os.path.isdir(d):
        return jsonify({"ok": False, "error": "目录不存在"}), 404
    dirs, files = [], []
    for name in os.listdir(d):
        p = os.path.join(d, name)
        try:
            st = os.stat(p)
        except OSError:
            continue
        mt = datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
        if os.path.isdir(p):
            dirs.append({"name": name, "type": "dir", "size": None, "modified": mt})
        else:
            files.append({"name": name, "type": "file", "size": st.st_size, "modified": mt})
    dirs.sort(key=lambda x: x["name"])
    files.sort(key=lambda x: x["name"])
    return jsonify({"ok": True, "data": {
        "path": _relname(d),           # 当前目录相对路径
        "items": dirs + files,
    }})


@bp.route("/upload", methods=["POST"])
@login_required
def upload():
    import sys
    d = _resolve(request.form.get("path", ""))
    if not d or not os.path.isdir(d):
        return jsonify({"ok": False, "error": "目标目录不存在"}), 404
    files = [f for f in request.files.getlist("file") if f and f.filename]
    clen = request.content_length or 0
    if not files:
        # 收到请求但解析不到文件：多为请求体被截断/超限（经 Cloudflare 免费版有 100MB 上限）
        print(f"[filebox] upload 未收到文件 content_length={clen} "
              f"form_keys={list(request.form.keys())} files_keys={list(request.files.keys())}",
              file=sys.stderr, flush=True)
        # 注意：clen 只是客户端声明的 Content-Length，不代表真的收全了。
        # 解析器在 multipart 中途遇到 EOF 会抛 ValueError，被 Werkzeug 静默吞掉，
        # 已解析出的字段（如 path）也一并丢弃 → form/files 双空。所以「双空且
        # clen 很大」= 传输被掐断，而不是文件太大被拒。
        if clen < 1024:
            hint = "（请求体几乎为空，多为前端未正确以 multipart 发送，请强刷页面重试）"
        elif not request.form:
            hint = ("（上传中途被中断：浏览器超时、切走页面或网络掉线都会这样，"
                    "请重试；经公网访问时另有 Cloudflare 100MB 上限，大文件请走局域网 172.1.14.12:1573）")
        else:
            hint = "（表单已收到但没有文件字段，请重新选择文件）"
        return jsonify({"ok": False,
                        "error": f"未收到文件（客户端声明 {clen // 1024 // 1024} MB）{hint}"}), 400
    # 文件夹上传：前端以文件的相对路径（webkitRelativePath）作为 filename 传来，
    # 需在目标目录内还原子目录结构；否则退化为按文件名平铺保存。
    preserve = request.form.get("preserve_paths") == "1"
    saved, skipped = 0, []
    for f in files:
        raw = (f.filename or "").replace("\\", "/")   # 归一 Windows 反斜杠
        if preserve and "/" in raw:
            # 逐段清洗，剔除空段/./..，防目录穿越
            segs = [s for s in raw.split("/") if s and s not in (".", "..")]
            if not segs:
                skipped.append(f.filename or "(空名)")
                continue
            dest = os.path.abspath(os.path.join(d, *segs))
            if os.path.commonpath([dest, FILEBOX_ROOT]) != FILEBOX_ROOT:
                skipped.append(raw)
                continue
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                f.save(dest)
                saved += 1
            except Exception as e:
                skipped.append(f"{raw}（{e}）")
            continue
        name = os.path.basename(raw)
        if not name or name in (".", ".."):
            skipped.append(f.filename or "(空名)")
            continue
        try:
            f.save(os.path.join(d, name))
            saved += 1
        except Exception as e:                      # 单个文件失败不连累整批
            skipped.append(f"{name}（{e}）")
    msg = f"已上传 {saved} 个文件"
    if skipped:
        msg += f"；跳过 {len(skipped)} 个：{'、'.join(skipped[:5])}"
    print(f"[filebox] upload saved={saved} skipped={len(skipped)} content_length={clen}",
          file=sys.stderr, flush=True)
    if saved == 0:
        return jsonify({"ok": False, "error": msg}), 400
    return jsonify({"ok": True, "message": msg})


@bp.route("/download", methods=["GET"])
@login_required
def download():
    p = _resolve(request.args.get("path", ""))
    if not p or not os.path.isfile(p):
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    return send_file(p, as_attachment=True, download_name=os.path.basename(p))


@bp.route("/download-folder", methods=["GET"])
@login_required
def download_folder():
    """把整个文件夹打包成 zip 下载（保留内部子目录结构）。"""
    import tempfile
    import zipfile
    from flask import after_this_request

    d = _resolve(request.args.get("path", ""))
    if not d or not os.path.isdir(d):
        return jsonify({"ok": False, "error": "文件夹不存在"}), 404
    base = os.path.basename(d) or "filebox"

    fd, tmp = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _dirs, fnames in os.walk(d):
                for fn in fnames:
                    full = os.path.join(root, fn)
                    if not os.path.isfile(full):
                        continue
                    arc = os.path.join(base, os.path.relpath(full, d))
                    z.write(full, arc)
                # 保留空目录
                if not fnames and not _dirs and root != d:
                    z.writestr(os.path.join(base, os.path.relpath(root, d)) + "/", "")
    except Exception as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return jsonify({"ok": False, "error": f"打包失败：{e}"}), 500

    @after_this_request
    def _cleanup(resp):
        # Linux 上 send_file 持有打开的 fd，unlink 后仍可完成流式传输
        try:
            os.remove(tmp)
        except OSError:
            pass
        return resp

    return send_file(tmp, as_attachment=True, download_name=f"{base}.zip")


@bp.route("/preview", methods=["GET"])
@login_required
def preview():
    """内联预览（PDF/图片浏览器渲染，docx/xlsx 前端渲染，html iframe）。"""
    p = _resolve(request.args.get("path", ""))
    if not p or not os.path.isfile(p):
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    from services.office_convert import send_preview
    return send_preview(p, os.path.basename(p))


@bp.route("/mkdir", methods=["POST"])
@login_required
def mkdir():
    data = request.get_json(force=True) or {}
    parent = _resolve(data.get("path", ""))
    name = (data.get("name") or "").strip()
    if not parent or not os.path.isdir(parent):
        return jsonify({"ok": False, "error": "父目录不存在"}), 404
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        return jsonify({"ok": False, "error": "文件夹名非法"}), 400
    target = os.path.join(parent, name)
    if os.path.exists(target):
        return jsonify({"ok": False, "error": "已存在同名文件/文件夹"}), 400
    os.makedirs(target)
    return jsonify({"ok": True, "message": "已新建文件夹"})


@bp.route("/delete", methods=["POST"])
@login_required
def delete():
    data = request.get_json(force=True) or {}
    p = _resolve(data.get("path", ""))
    if not p or p == FILEBOX_ROOT or not os.path.exists(p):
        return jsonify({"ok": False, "error": "路径不存在或不可删"}), 404
    if os.path.isdir(p):
        shutil.rmtree(p)
    else:
        os.remove(p)
    return jsonify({"ok": True, "message": "已删除"})
