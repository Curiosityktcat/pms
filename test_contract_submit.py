#!/usr/bin/env python3
"""合同审签单自动提交测试脚本（直接运行，不需要启动Flask）。

用法：
  cd /home/huangxb/pms
  python test_contract_submit.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from services.contract_submit import submit_contract

TEST_DATA = {
    "合同名称":       "测试合同-勿提交",
    "合同编码":       "TEST-2026-001",
    "项目名称及包号": "测试项目 第一包",
    "归口管理科室":   "采购部",
    "合同金额":       "¥100,000.00",
    "合同甲方":       "测试甲方单位",
    "甲方法定代表人": "张三",
    "甲方联系电话":   "010-12345678",
    "甲方地址":       "北京市朝阳区测试路1号",
    "合同乙方":       "测试乙方公司",
    "乙方法定代表人": "李四",
    "乙方联系电话":   "010-87654321",
    "乙方地址":       "上海市浦东新区测试街2号",
    "合同类别":       "采购部合同",
    "经办人":         "黄新博",
}

if __name__ == "__main__":
    print("=" * 60)
    print("开始测试合同审签单自动提交（无附件，仅填表不提交）")
    print("=" * 60)

    # 带一个测试附件文件跑完整流程（包含提交）
    # 用 /tmp/test_contract.txt 作占位附件；正式使用时换成真实合同文件路径
    result = submit_contract(TEST_DATA, file_path="/tmp/test_contract.txt")
    print("\n【结果】")
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result["ok"]:
        print(f"\n✓ 提交成功，流水号: {result['serial_no']}")
    else:
        print(f"\n✗ 提交失败: {result['msg']}")
        if result.get("detail"):
            print("详细信息:", json.dumps(result["detail"], ensure_ascii=False, indent=2))
