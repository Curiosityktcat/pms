#!/usr/bin/env python3
"""合同审签单自动化诊断脚本。

模式：
  python diagnose_contract.py        → 导航+截图，不填任何字段
  python diagnose_contract.py fill   → 填写全部字段+选类别+选经办人，但不上传/不提交（可人工核查截图后关掉）

截图保存在 /tmp/contract_diag_*.png
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

STATE_PATH = os.path.expanduser('~/pms/.rdweb_session.json')
LOGIN_URL  = 'https://rd-web.mobimedical.cn/'
APP_MARK   = '6642c01d66eb836a97bbccb2'

TEST_DATA = {
    "合同名称":       "【测试-勿提交】测试合同2026",
    "合同编码":       "TEST-2026-001",
    "项目名称及包号": "测试项目 第一包",
    "归口管理科室":   "采购部",
    "合同金额":       "100000",
    "合同甲方":       "测试甲方单位",
    "甲方法定代表人": "张三",
    "甲方联系电话":   "010-12345678",
    "甲方地址":       "北京市测试路1号",
    "合同乙方":       "测试乙方公司",
    "乙方法定代表人": "李四",
    "乙方联系电话":   "010-87654321",
    "乙方地址":       "上海市测试街2号",
    "合同类别":       "采购部合同",
    "经办人":         "黄新博",
}

FILL_MODE = len(sys.argv) > 1 and sys.argv[1] == 'fill'


def snap(pg, name):
    p = f'/tmp/contract_diag_{name}.png'
    pg.screenshot(path=p, full_page=False)
    print(f'  📸 {p}')


def main():
    from playwright.sync_api import sync_playwright
    from services.contract_submit import (
        _wait_frame, _login_if_needed, _nav_to_contract, _open_form,
        _fill_text_fields, _select_category, _fill_officer, TEXT_FIELDS
    )

    print(f'=== rd-web 合同审签单诊断（{"填写模式" if FILL_MODE else "只读模式"}）===\n')

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel='chrome', headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        ctx_args = {'viewport': {'width': 1920, 'height': 1080},
                    'user_agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0'}
        if os.path.exists(STATE_PATH):
            ctx_args['storage_state'] = STATE_PATH
            print(f'✓ 使用 session: {STATE_PATH}')
        else:
            print('✗ 无 session，需要登录')

        ctx = browser.new_context(**ctx_args)
        pg  = ctx.new_page()

        try:
            # 1. 登录
            print('\n[1] 登录检查…')
            pg.goto(LOGIN_URL, wait_until='networkidle', timeout=30000)
            pg.wait_for_timeout(2000)
            snap(pg, '01_home')
            has_login = pg.locator('#loginBtn').count() > 0
            print(f'  需要登录: {has_login}')
            if has_login:
                user = input('  账号 [13029144451]: ').strip() or '13029144451'
                pwd  = input('  密码: ').strip()
                pg.fill('#loginUser', user)
                pg.fill('#password', pwd)
                pg.click('#loginBtn')
                pg.wait_for_timeout(3500)
                ctx.storage_state(path=STATE_PATH)
                print(f'  ✓ 登录并保存 session')
            else:
                print('  ✓ session 有效，已跳过登录')

            # 2. 导航
            print('\n[2] 点击「合同审签单」…')
            fr = _nav_to_contract(pg)
            snap(pg, '02_list')
            print(f'  ✓ frame URL: {fr.url[:80]}')

            # 3. 打开表单
            print('\n[3] 点击「发起」打开表单…')
            _open_form(fr, pg)
            snap(pg, '03_form')
            print('  ✓ 表单已打开')

            # 4. 检查可见输入框
            from services.contract_submit import _visible_inputs
            inputs = _visible_inputs(fr)
            print(f'\n[4] 可见 placeholder="请输入" 的输入框数量: {len(inputs)}（期望≥13）')
            for i, loc in enumerate(inputs[:15]):
                try:
                    box = loc.bounding_box()
                    print(f'  [{i}] y={box["y"]:.0f} h={box["height"]:.0f}')
                except Exception as e:
                    print(f'  [{i}] 获取位置失败: {e}')

            # 5. 检查 radio
            radio_loc = fr.locator("i[class*='attend-radio']")
            visible_radios = [radio_loc.nth(i) for i in range(radio_loc.count())
                              if radio_loc.nth(i).is_visible()]
            print(f'\n[5] 合同类别 radio 数量: {len(visible_radios)}（期望3）')

            # 6. 检查附件按钮
            add_btn = fr.locator("[class*='item-customer-add']")
            has_add = add_btn.count() > 0 and add_btn.first.is_visible()
            print(f'\n[6] 「添加附件」按钮: {"找到" if has_add else "未找到"}')

            # 7. 如果是填写模式，执行填写
            if FILL_MODE:
                print('\n[7] 填写模式：填写全部文本字段…')
                field_values = [TEST_DATA.get(f, '') for f in TEXT_FIELDS]
                try:
                    res = _fill_text_fields(fr, pg, field_values)
                    print(f'  ✓ 文本字段填写: {res}')
                except Exception as e:
                    print(f'  ✗ 文本字段填写失败: {e}')
                snap(pg, '04_filled_text')

                print('\n[8] 选择合同类别…')
                try:
                    cat = _select_category(fr, pg, TEST_DATA['合同类别'])
                    print(f'  ✓ 合同类别: {cat}')
                except Exception as e:
                    print(f'  ✗ 合同类别选择失败: {e}')
                snap(pg, '05_category')

                print('\n[9] 填写经办人…')
                try:
                    ofc = _fill_officer(fr, pg, TEST_DATA['经办人'])
                    print(f'  ✓ 经办人: {ofc}')
                except Exception as e:
                    print(f'  ✗ 经办人填写失败: {e}')
                snap(pg, '06_officer')

                print('\n  ⚠ 填写完成，未点提交。请查看截图确认填写效果。')
            else:
                print('\n  提示：运行 python diagnose_contract.py fill 可进入填写模式')

            snap(pg, '99_final')

        except Exception as e:
            print(f'\n✗ 发生错误: {e}')
            try:
                snap(pg, 'error')
            except Exception:
                pass

        ctx.storage_state(path=STATE_PATH)
        browser.close()
        print('\n=== 诊断结束，截图在 /tmp/contract_diag_*.png ===')


if __name__ == '__main__':
    main()
