import { useEffect, useState } from 'react'
import {
  Form, Input, InputNumber, Select, Checkbox, Radio, Button, Card,
  Space, Divider, Typography, App, Descriptions, Alert, DatePicker,
} from 'antd'
import dayjs from 'dayjs'
import type { CheckboxChangeEvent } from 'antd/es/checkbox'

// 开标时间：DatePicker 用 dayjs，存库用中文串 "2026年5月27日16:00"（无空格，兼容各处抓取正则）
function parseCnDateTime(s?: string): dayjs.Dayjs | null {
  if (!s) return null
  const m = s.match(/(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*(?:(\d{1,2})\s*[：:]\s*(\d{2}))?/)
  if (!m) return null
  const d = dayjs(new Date(+m[1], +m[2] - 1, +m[3], m[4] ? +m[4] : 0, m[5] ? +m[5] : 0))
  return d.isValid() ? d : null
}
function fmtCnDateTime(d?: dayjs.Dayjs | null): string {
  return d ? d.format('YYYY年M月D日HH:mm') : ''
}
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  getProjectMeta, getProject, createProject, updateProject,
} from '../services/project'
import type { Agency } from '../services/project'
import { listDistributions, type Distribution } from '../services/projectDistribution'
import { autoPushText } from '../services/rdwebApproval'
import { useAuth } from '../hooks/useAuth'

const { TextArea } = Input
const { Text } = Typography

// 「项目分发」采购方式 → 立项采购方式
const DIST_METHOD_MAP: Record<string, string> = {
  '院内竞选': '院内竞选',
  '院内单一来源采购': '院内单一来源采购',
  '院内询价': '院内询价',
  '院内议价': '院内议价',
  '医用耗材紧急采购': '医用耗材紧急采购',
}

const M_YIJIA  = '院内议价'
const M_XUNJIA = '院内询价'
const M_JINGXUAN = '院内竞选'
const M_SOLE   = '院内单一来源采购'
const M_JINGJI = '医用耗材紧急采购'

const METHOD_HINT: Record<string, string> = {
  [M_YIJIA]:   '2万以下的货物/工程/服务',
  [M_XUNJIA]:  '2万(含)～5万',
  [M_JINGXUAN]:'5万(含)以上；一般委托代理机构，也可不走代理（下方选择）',
  [M_SOLE]:    '需专家论证+公示；可走可不走代理（下方选择）',
  [M_JINGJI]:  '医用耗材紧急采购，不分金额，不走代理机构',
}

function autoMethod(amount: number | null, isUnitPrice: boolean): string {
  if (isUnitPrice) return M_JINGXUAN
  if (!amount) return M_YIJIA
  if (amount < 20000) return M_YIJIA
  if (amount < 50000) return M_XUNJIA
  return M_JINGXUAN
}

export default function ProjectFormPage() {
  const { id } = useParams<{ id?: string }>()
  const [searchParams] = useSearchParams()
  const fromDemandId = searchParams.get('from_demand')  // 从采购需求立项时传入
  const fromDistId = searchParams.get('from_dist')      // 从「2.1项目分发」点立项时传入，自动选中并预填
  const isEdit = !!id
  const navigate = useNavigate()
  const { user } = useAuth()
  const { message } = App.useApp()
  const [form] = Form.useForm()

  const [agencies, setAgencies] = useState<Agency[]>([])
  const [statuses, setStatuses] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [pageLoading, setPageLoading] = useState(isEdit)
  const [isDraft, setIsDraft] = useState(false)
  const [isLocked, setIsLocked] = useState(false) // 已正式立项，编号锁定
  const [lockedNumber, setLockedNumber] = useState('')
  const [lockedLine, setLockedLine] = useState('')
  const [lockedAgencyCode, setLockedAgencyCode] = useState('')
  const [demandId, setDemandId] = useState<number | null>(null)       // 关联采购需求ID
  const [demandType, setDemandType] = useState<string>('')             // 'gov' 时正式立项后自动归档
  const [distributions, setDistributions] = useState<Distribution[]>([])  // 分发给我、待立项的项目
  const [distributionId, setDistributionId] = useState<number | null>(null)

  // 监听表单字段
  const methodVal = Form.useWatch('method', form)
  const isUnitPrice = Form.useWatch('is_unit_price', form)
  const soleUseAgency = Form.useWatch('sole_use_agency', form)

  // 紧急采购永不走代理；竞选默认走代理（99% 委托代理），单一来源默认不走。
  // 两者都能在下拉里改，字段沿用 sole_use_agency（后端也认这个名字）。
  const needsAgency =
    (methodVal === M_JINGXUAN && soleUseAgency !== 'no') ||
    (methodVal === M_SOLE && soleUseAgency === 'yes')
  const canChooseAgency = methodVal === M_JINGXUAN || methodVal === M_SOLE
  // 紧急采购：金额变化不改变采购方式
  const isJingji = methodVal === M_JINGJI

  useEffect(() => {
    const loadMeta = async () => {
      try {
        const res = await getProjectMeta()
        setAgencies(res.data.agencies)
        setStatuses(res.data.statuses)
      } catch {
        message.error('加载基础数据失败')
      }
    }
    loadMeta()
  }, [])

  // 用一条分发记录预填立项表单
  const fillFromDist = (d: Distribution) => {
    setDistributionId(d.id)
    form.setFieldsValue({
      name: d.name,
      content: d.content || undefined,
      amount: d.budget || null,
      is_unit_price: !d.budget,
      method: DIST_METHOD_MAP[d.method] || undefined,
      agency_code: d.agency_code || undefined,
      sole_use_agency: d.method === '院内单一来源采购' ? 'yes' : undefined,
      // 审签表里本来就有的三项，立项时一并带过来（原来漏了，每次都要手工重填）
      demand_dept: d.demand_dept || undefined,
      manage_dept: d.manage_dept || undefined,
      // 池里的「项目所属分类」取值就是 货物/服务/工程，与立项的采购项目分类同一套
      category: ['货物', '服务', '工程'].includes(d.form_type) ? d.form_type : undefined,
    })
  }

  // 新立项时拉「分发给我、待立项」的项目；若带 from_dist 参数则自动选中预填
  useEffect(() => {
    if (isEdit || fromDemandId) return
    listDistributions()
      .then(res => {
        const mine = (res.data.data || []).filter(
          d => d.status === '已分发' && d.officer === user?.display_name)
        setDistributions(mine)
        if (fromDistId) {
          const d = mine.find(x => x.id === Number(fromDistId))
          if (d) fillFromDist(d)
        }
      })
      .catch(() => {})
  }, [isEdit, fromDemandId, fromDistId, user?.display_name]) // eslint-disable-line react-hooks/exhaustive-deps

  const applyDistribution = (did: number | null) => {
    if (!did) { setDistributionId(null); return }
    const d = distributions.find(x => x.id === did)
    if (d) fillFromDist(d)
  }

  useEffect(() => {
    if (!isEdit) {
      // 默认值
      form.setFieldsValue({
        officer: user?.display_name || '',
        method: M_YIJIA,
        year: `${new Date().getFullYear()}年`,
      })
      // 从采购需求立项时，读取 sessionStorage 中的预填数据
      if (fromDemandId) {
        try {
          const raw = sessionStorage.getItem('demand_prefill')
          if (raw) {
            const pf = JSON.parse(raw)
            if (String(pf.demand_id) === fromDemandId) {
              setDemandId(pf.demand_id)
              setDemandType(pf.demand_type || '')
              // 采购需求里的方式映射到立项表单的采购方式
              const methodMap: Record<string, string> = {
                '院内竞选': M_JINGXUAN,
                '院内单一来源': M_SOLE,
                '院内询价': M_XUNJIA,
                '院内议价': M_YIJIA,
              }
              form.setFieldsValue({
                name: pf.name,
                category: pf.category,
                year: pf.year || `${new Date().getFullYear()}年`,
                amount: pf.amount || null,
                method: methodMap[pf.method] || M_YIJIA,
                agency_code: pf.agency_code || undefined,
                demand_dept: pf.demand_dept,
                manage_dept: pf.manage_dept,
                content: pf.content,
                officer: pf.officer || user?.display_name || '',
              })
              sessionStorage.removeItem('demand_prefill')
            }
          }
        } catch { /* ignore */ }
      }
      return
    }
    const load = async () => {
      try {
        const res = await getProject(Number(id))
        const p = res.data.data
        setAgencies(res.data.agencies)
        setStatuses(res.data.statuses)
        setIsDraft(p.is_draft)
        if (!p.is_draft) {
          setIsLocked(true)
          setLockedNumber(p.number)
          setLockedLine(p.line)
          setLockedAgencyCode(p.agency_code)
        }
        form.setFieldsValue({
          name: p.name,
          amount: (p.amount && p.amount > 0) ? p.amount : null,
          is_unit_price: !p.amount || p.amount === 0,
          method: p.method,
          sole_use_agency: p.line === 'C' ? 'yes' : 'no',
          agency_code: p.agency_code,
          demand_dept: p.demand_dept,
          manage_dept: p.manage_dept,
          officer: p.officer,
          content: p.content,
          bid_time: parseCnDateTime(p.bid_time),
          status: p.status,
          category: p.category,
          year: p.year,
        })
      } catch (err: any) {
        message.error(err.response?.data?.error || '加载项目失败')
        navigate('/flow')
      } finally {
        setPageLoading(false)
      }
    }
    load()
  }, [id])

  const handleAmountChange = (val: number | null) => {
    if (isLocked) return
    const cur = form.getFieldValue('method')
    // 单一来源和紧急采购是手动选择，金额变化不自动覆盖
    if (cur === M_SOLE || cur === M_JINGJI) return
    form.setFieldValue('method', autoMethod(val, false))
  }

  const handleUnitPriceChange = (e: CheckboxChangeEvent) => {
    if (isLocked) return
    const checked = e.target.checked
    if (checked) {
      form.setFieldValue('amount', null)
      form.setFieldValue('method', M_JINGXUAN)
      form.setFieldValue('sole_use_agency', 'yes')
    } else {
      form.setFieldValue('method', autoMethod(form.getFieldValue('amount'), false))
    }
  }

  const submit = async (action: 'submit' | 'draft') => {
    try {
      await form.validateFields()
    } catch {
      return
    }
    const values = form.getFieldsValue()
    // 开标时间日历控件返回 dayjs，转回中文串存库（无空格，确保各处可正确抓取）
    if ('bid_time' in values) values.bid_time = fmtCnDateTime(values.bid_time)
    // 从采购需求立项时，附带 demand_id + demand_type 让后端自动标记需求和处理归档
    const payload = {
      ...values, action,
      ...(demandId ? { demand_id: demandId } : {}),
      ...(demandType ? { demand_type: demandType } : {}),
      ...(distributionId ? { distribution_id: distributionId } : {}),
    }

    setLoading(true)
    try {
      let res
      if (isEdit) {
        res = await updateProject(Number(id), payload)
      } else {
        res = await createProject(payload)
      }
      message.success(res.data.message)
      // 立项且选定代理 → 后端已自动把委托代理协议推去 rd-web 审签
      const pushTip = autoPushText((res.data as any)?.rdweb_push)
      if (pushTip) message.info(pushTip)
      // 若从需求立项成功，回到需求页面查看已立项状态
      navigate(demandId && action === 'submit' ? '/procurement-demand' : '/flow')
    } catch (err: any) {
      message.error(err.response?.data?.error || '操作失败')
    } finally {
      setLoading(false)
    }
  }

  if (pageLoading) return <Card loading />

  const title = isEdit ? (isDraft ? '编辑草稿（可正式立项）' : '编辑项目') : '项目立项'

  return (
    <Card>
      <div style={{ fontSize: 18, fontWeight: 600, color: '#2c3e50', marginBottom: 20 }}>{title}</div>

      {demandId && !isEdit && (
        <Alert
          type="info" showIcon style={{ marginBottom: 16 }}
          message={`正在从采购需求（ID: ${demandId}）立项 —— 可修改名称、金额、采购方式后点击「正式立项」。`}
        />
      )}

      {!isEdit && !fromDemandId && distributions.length > 0 && (
        <Alert
          type="success" showIcon style={{ marginBottom: 16 }}
          message={
            <Space wrap>
              <span>从「项目分发」立项（自动带入名称/内容/预算/方式/代理，可改）：</span>
              <Select
                allowClear style={{ minWidth: 280 }} placeholder="选择分发给我的项目"
                value={distributionId ?? undefined}
                onChange={(v) => applyDistribution(v ?? null)}
                options={distributions.map(d => ({
                  value: d.id,
                  label: `${d.name}${d.serial_no ? `（${d.serial_no}）` : ''}`,
                }))}
              />
            </Space>
          }
        />
      )}

      {isLocked && (
        <Descriptions size="small" bordered style={{ marginBottom: 20 }} column={3}>
          <Descriptions.Item label="项目编号">
            <Text strong>{lockedNumber}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="流程线">线 {lockedLine}</Descriptions.Item>
          <Descriptions.Item label="代理机构">
            {lockedAgencyCode
              ? agencies.find(a => a.code === lockedAgencyCode)?.name || lockedAgencyCode
              : <Text type="secondary">无</Text>}
          </Descriptions.Item>
        </Descriptions>
      )}

      <Form form={form} layout="vertical" size="middle">
        <div style={{ display: 'flex', gap: 16 }}>
          <Form.Item
            label="项目名称"
            name="name"
            rules={[{ required: true, message: '请填写项目名称' }]}
            style={{ flex: 1 }}
          >
            <Input placeholder="如：2026年XX耗材采购项目" />
          </Form.Item>
        </div>

        <div style={{ display: 'flex', gap: 16 }}>
          <Form.Item
            label="采购项目分类"
            name="category"
            rules={[{ required: true, message: '请选择分类' }]}
            style={{ flex: 1 }}
          >
            <Radio.Group>
              <Radio value="货物">货物</Radio>
              <Radio value="服务">服务</Radio>
              <Radio value="工程">工程</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item
            label="采购年度"
            name="year"
            rules={[{ required: true, message: '请填写采购年度' }]}
            style={{ width: 140 }}
          >
            <Select options={
              Array.from({ length: 5 }, (_, i) => {
                const y = `${new Date().getFullYear() - 1 + i}年`
                return { value: y, label: y }
              })
            } />
          </Form.Item>
        </div>

        <div style={{ display: 'flex', gap: 16 }}>
          <Form.Item label="预算金额（元）" name="amount" style={{ flex: 1 }}>
            <InputNumber
              style={{ width: '100%' }}
              placeholder="填具体金额"
              min={0}
              step={1000}
              disabled={isUnitPrice}
              onChange={handleAmountChange}
              formatter={(v) => v ? `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',') : ''}
              parser={(v) => v?.replace(/,/g, '') as any}
            />
          </Form.Item>
          <Form.Item label=" " name="is_unit_price" valuePropName="checked" style={{ flex: 1, marginTop: 4 }}>
            <Checkbox onChange={handleUnitPriceChange} disabled={isLocked}>
              挂网耗材/招单价（无固定预算，按≥5万竞选）
            </Checkbox>
          </Form.Item>
        </div>

        <div style={{ display: 'flex', gap: 16 }}>
          <Form.Item label="采购方式（按金额自动，可手动改为单一来源或紧急采购）" name="method" style={{ flex: 1 }}>
            <Select
              disabled={isLocked}
              onChange={(m: string) => {
                // 每种方式的默认走代理口径不同：竞选默认走、单一来源默认不走
                if (m === M_JINGXUAN) form.setFieldValue('sole_use_agency', 'yes')
                else if (m === M_SOLE) form.setFieldValue('sole_use_agency', 'no')
              }}
              options={[
                { value: M_YIJIA,   label: M_YIJIA },
                { value: M_XUNJIA,  label: M_XUNJIA },
                { value: M_JINGXUAN,label: M_JINGXUAN },
                { value: M_SOLE,    label: M_SOLE },
                { value: M_JINGJI,  label: M_JINGJI,
                  // 紧急采购在已锁定时不可切换（同单一来源逻辑）
                  disabled: isLocked },
              ]}
            />
          </Form.Item>
          {methodVal && (
            <Form.Item label=" " style={{ flex: 1 }}>
              <Text type="secondary" style={{ fontSize: 13 }}>{METHOD_HINT[methodVal]}</Text>
            </Form.Item>
          )}
        </div>

        {canChooseAgency && !isLocked && (
          <Form.Item label="是否走代理机构？" name="sole_use_agency" style={{ maxWidth: 320 }}>
            <Select options={[
              { value: 'no', label: '不走代理（NJYYXJ）' },
              { value: 'yes', label: '走代理（NJYYJX）' },
            ]} />
          </Form.Item>
        )}

        <div style={{ display: 'flex', gap: 16 }}>
          {!isJingji && (
            <Form.Item
              label="代理机构（走代理时必选）"
              name="agency_code"
              style={{ flex: 1 }}
              rules={[{
                validator: (_, val) =>
                  needsAgency && !val
                    ? Promise.reject('走代理的项目必须选择代理机构')
                    : Promise.resolve(),
              }]}
            >
              <Select
                allowClear
                placeholder="（不走代理免选）"
                options={agencies.map(a => ({ value: a.code, label: a.name }))}
              />
            </Form.Item>
          )}
          <Form.Item label="项目经办人" name="officer" style={{ flex: 1 }}>
            <Input disabled={user?.role === 'officer'} />
          </Form.Item>
        </div>

        <div style={{ display: 'flex', gap: 16 }}>
          <Form.Item label="需求科室" name="demand_dept" style={{ flex: 1 }}>
            <Input />
          </Form.Item>
          <Form.Item label="归口管理科室" name="manage_dept" style={{ flex: 1 }}>
            <Input />
          </Form.Item>
        </div>

        {isEdit && !isDraft && (
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item label="当前状态" name="status" style={{ flex: 1 }}>
              <Select options={statuses.map(s => ({ value: s, label: s }))} />
            </Form.Item>
            <Form.Item label="开标时间" name="bid_time" style={{ flex: 1 }}>
              <DatePicker
                showTime={{ format: 'HH:mm' }}
                format="YYYY年M月D日HH:mm"
                style={{ width: '100%' }}
                placeholder="选择开标日期时间"
              />
            </Form.Item>
          </div>
        )}

        <Form.Item label="包号及采购内容" name="content">
          <TextArea rows={3} />
        </Form.Item>

        <Divider />
        <Space>
          <Button type="primary" loading={loading} onClick={() => submit('submit')}>
            {isDraft ? '正式立项（生成编号）' : isEdit ? '保存修改' : '正式立项（生成编号）'}
          </Button>
          {(!isEdit || isDraft) && (
            <Button onClick={() => submit('draft')} loading={loading}>存草稿</Button>
          )}
          <Button onClick={() => navigate('/flow')}>取消</Button>
        </Space>
      </Form>
    </Card>
  )
}
