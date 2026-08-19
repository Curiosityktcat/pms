/**
 * 分包编辑：每个包一份第四~第八部分。
 *
 * 黄新博 2026-08-19 ⑥⑪：「每个包就是一个独立的合同，具体需求与实施情况都不一样」，
 * 并明确要「能复制上一个包」——多数项目各包只差几个参数，从头填一遍太苦。
 */
import { Button, Col, Input, InputNumber, Popconfirm, Radio, Row, Space, Tabs, Tag, Typography } from 'antd'
import { CopyOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons'

const { TextArea } = Input
const { Text } = Typography

export interface EvalCell { 分值?: number; 客观项?: string; 标准?: string }
export interface PackageData {
  预算金额?: number
  最高限价?: number
  评审方法?: string
  定价方式?: string
  是否支持联合体投标?: string
  是否允许合同分包?: string
  技术要求?: string
  商务要求?: string
  特殊资格要求?: string
  评审因素?: Record<string, EvalCell>
}

const CN = '一二三四五六七八九十'
export const cn = (n: number) => (n >= 1 && n <= 10 ? CN[n - 1] : String(n))

const EVAL_ROWS = ['价格分', '技术要求', '服务要求', '价格扣除']

export const emptyPackage = (): PackageData => ({
  评审方法: '综合评分法', 定价方式: '固定单价',
  是否支持联合体投标: '否', 是否允许合同分包: '否', 评审因素: {},
})

export default function PackageEditor(
  { value, onChange, activeKey, onActiveChange }:
  {
    value: PackageData[]
    onChange: (v: PackageData[]) => void
    activeKey?: string
    onActiveChange?: (k: string) => void
  },
) {
  const pkgs = value.length ? value : [emptyPackage()]

  const setPkg = (i: number, patch: Partial<PackageData>) => {
    const next = pkgs.map((p, j) => (j === i ? { ...p, ...patch } : p))
    onChange(next)
  }
  const setEval = (i: number, row: string, patch: Partial<EvalCell>) => {
    const cur = pkgs[i].评审因素 || {}
    setPkg(i, { 评审因素: { ...cur, [row]: { ...(cur[row] || {}), ...patch } } })
  }
  const addPkg = (copyFrom?: number) => {
    // 「复制上一个包」：把上一个包整个拷过来，只留人去改差异的那几项
    const src = copyFrom != null ? JSON.parse(JSON.stringify(pkgs[copyFrom])) : emptyPackage()
    onChange([...pkgs, src])
    onActiveChange?.(String(pkgs.length))
  }
  const delPkg = (i: number) => {
    const next = pkgs.filter((_, j) => j !== i)
    onChange(next.length ? next : [emptyPackage()])
    onActiveChange?.('0')
  }

  return (
    <Tabs
      type="card"
      activeKey={activeKey}
      onChange={onActiveChange}
      tabBarExtraContent={
        <Space size={6}>
          <Button size="small" icon={<CopyOutlined />}
            onClick={() => addPkg(pkgs.length - 1)}>
            复制上一个包
          </Button>
          <Button size="small" icon={<PlusOutlined />} onClick={() => addPkg()}>
            新增空包
          </Button>
        </Space>
      }
      items={pkgs.map((p, i) => ({
        key: String(i),
        label: `合同包${cn(i + 1)}`,
        children: (
          <div>
            <Row gutter={[12, 10]}>
              <Col span={8}>
                <Text style={{ fontSize: 13 }}>4.2.1 预算金额（元）</Text>
                <InputNumber style={{ width: '100%' }} value={p.预算金额}
                  onChange={v => setPkg(i, { 预算金额: v ?? undefined })} />
              </Col>
              <Col span={8}>
                <Text style={{ fontSize: 13 }}>最高限价（元）</Text>
                <InputNumber style={{ width: '100%' }} value={p.最高限价}
                  onChange={v => setPkg(i, { 最高限价: v ?? undefined })} />
              </Col>
              <Col span={8}>
                <Text style={{ fontSize: 13 }}>4.2.3 定价方式</Text>
                <Radio.Group value={p.定价方式} style={{ display: 'block', marginTop: 4 }}
                  onChange={e => setPkg(i, { 定价方式: e.target.value })}>
                  <Radio value="固定单价">固定单价</Radio>
                  <Radio value="固定总价">固定总价</Radio>
                </Radio.Group>
              </Col>
              <Col span={12}>
                <Text style={{ fontSize: 13 }}>4.2.2 评审方法</Text>
                <Radio.Group value={p.评审方法} style={{ display: 'block', marginTop: 4 }}
                  onChange={e => setPkg(i, { 评审方法: e.target.value })}>
                  <Radio value="最低评标价法">最低评标价法</Radio>
                  <Radio value="综合评分法">综合评分法</Radio>
                </Radio.Group>
              </Col>
              <Col span={6}>
                <Text style={{ fontSize: 13 }}>4.2.4 支持联合体</Text>
                <Radio.Group value={p.是否支持联合体投标} style={{ display: 'block', marginTop: 4 }}
                  onChange={e => setPkg(i, { 是否支持联合体投标: e.target.value })}>
                  <Radio value="是">是</Radio><Radio value="否">否</Radio>
                </Radio.Group>
              </Col>
              <Col span={6}>
                <Text style={{ fontSize: 13 }}>4.2.5 允许合同分包</Text>
                <Radio.Group value={p.是否允许合同分包} style={{ display: 'block', marginTop: 4 }}
                  onChange={e => setPkg(i, { 是否允许合同分包: e.target.value })}>
                  <Radio value="是">是</Radio><Radio value="否">否</Radio>
                </Radio.Group>
              </Col>

              <Col span={24}>
                <Text style={{ fontSize: 13 }}>第五部分：技术要求</Text>
                <TextArea rows={3} value={p.技术要求}
                  placeholder="★ 为实质性条款，▲ 为重要条款；条目式书写。也可以直接粘一张表格进来"
                  onChange={e => setPkg(i, { 技术要求: e.target.value })} />
              </Col>
              <Col span={24}>
                <Text style={{ fontSize: 13 }}>第六部分：商务要求</Text>
                <TextArea rows={2} value={p.商务要求}
                  onChange={e => setPkg(i, { 商务要求: e.target.value })} />
              </Col>
              <Col span={24}>
                <Text style={{ fontSize: 13 }}>第七部分：供应商特殊资格要求</Text>
                <TextArea rows={2} value={p.特殊资格要求}
                  placeholder="一般资格要求是固定的 8 条，系统自动带；这里只填结合标的另设的特殊要求"
                  onChange={e => setPkg(i, { 特殊资格要求: e.target.value })} />
              </Col>

              <Col span={24}>
                <Text style={{ fontSize: 13 }}>第八部分：评审因素</Text>
                <div style={{ marginTop: 6 }}>
                  {EVAL_ROWS.map(row => {
                    const c = (p.评审因素 || {})[row] || {}
                    return (
                      <Row key={row} gutter={8} style={{ marginBottom: 6 }}>
                        <Col span={4}><Tag>{row}</Tag></Col>
                        <Col span={3}>
                          <InputNumber size="small" placeholder="分值" style={{ width: '100%' }}
                            value={c.分值} onChange={v => setEval(i, row, { 分值: v ?? undefined })} />
                        </Col>
                        <Col span={4}>
                          <Radio.Group size="small" value={c.客观项}
                            onChange={e => setEval(i, row, { 客观项: e.target.value })}>
                            <Radio value="是">客观</Radio><Radio value="否">主观</Radio>
                          </Radio.Group>
                        </Col>
                        <Col span={13}>
                          <Input size="small" placeholder="评审标准" value={c.标准}
                            onChange={e => setEval(i, row, { 标准: e.target.value })} />
                        </Col>
                      </Row>
                    )
                  })}
                </div>
              </Col>
            </Row>

            {pkgs.length > 1 && (
              <div style={{ textAlign: 'right', marginTop: 10 }}>
                <Popconfirm title={`删除合同包${cn(i + 1)}？`} onConfirm={() => delPkg(i)}>
                  <Button size="small" danger icon={<DeleteOutlined />}>删除这个包</Button>
                </Popconfirm>
              </div>
            )}
          </div>
        ),
      }))}
    />
  )
}
