/**
 * 合同审签推送（工具集合入口，不绑定合同管理记录）。
 *
 * 用途：手工把一份合同直接推送到 rd-web 合同审签单。
 * 亮点：把合同首页文字粘贴进来，AI 自动抽取并填写审签字段；
 *       附件上传后随单提交（rd-web 要求必须带附件）。
 */
import { useEffect, useRef, useState } from 'react'
import {
  Alert, Button, Card, Col, Form, Input, List, message, Modal, Radio, Row, Select,
  Space, Table, Tag, Typography, Upload,
} from 'antd'
import {
  DeleteOutlined, HistoryOutlined, InboxOutlined, KeyOutlined,
  RobotOutlined, SendOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import {
  autofillRdweb, getRdwebFields, getRdwebMyAccount, getRdwebRecords, getRdwebStatus,
  saveRdwebMyAccount, submitRdweb, uploadRdwebFile,
  type RdwebAttachment, type RdwebField, type RdwebMyAccount, type RdwebPushRecord, type RdwebStatus,
} from '../services/rdwebContract'

const { Title, Paragraph, Text } = Typography

type UploadedAtt = RdwebAttachment & { uid: string }

export default function RdwebContractPushPage() {
  const [form] = Form.useForm()
  const [fields, setFields] = useState<RdwebField[]>([])
  const [pasteText, setPasteText] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [attachments, setAttachments] = useState<UploadedAtt[]>([])
  const [aiUid, setAiUid] = useState('')           // 用于 AI 读取的附件 uid
  const [uploading, setUploading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [status, setStatus] = useState<RdwebStatus | null>(null)
  const [records, setRecords] = useState<RdwebPushRecord[]>([])
  const [account, setAccount] = useState<RdwebMyAccount | null>(null)
  const [acctOpen, setAcctOpen] = useState(false)
  const [acctForm] = Form.useForm()
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  const reloadRecords = () =>
    getRdwebRecords().then(r => setRecords(r.data.data || [])).catch(() => {})

  const reloadAccount = () =>
    getRdwebMyAccount().then(r => setAccount(r.data)).catch(() => {})

  useEffect(() => {
    getRdwebFields().then(r => setFields(r.data.fields || [])).catch(() => {})
    refreshStatus()
    reloadRecords()
    reloadAccount()
    return () => { if (pollTimer.current) clearInterval(pollTimer.current) }
  }, [])

  const refreshStatus = async () => {
    try {
      const r = await getRdwebStatus()
      setStatus(r.data.data)
      return r.data.data
    } catch { return null }
  }

  const startPolling = () => {
    if (pollTimer.current) clearInterval(pollTimer.current)
    pollTimer.current = setInterval(async () => {
      const s = await refreshStatus()
      if (s && !s.running) {
        if (pollTimer.current) clearInterval(pollTimer.current)
        setSubmitting(false)
        if (s.ok) message.success(`推送成功，流水号：${s.serial_no || '（见详情）'}`)
        else message.error(s.msg || '推送失败')
        reloadRecords()
      }
    }, 3000)
  }

  // ── AI 自动填写（附件优先；粘贴文字为兜底）──────────────────────
  const doAutofill = async (src: { text?: string; file_path?: string }) => {
    if (!src.file_path && (src.text || '').trim().length < 20) {
      message.warning('请先上传合同附件并选择要识别的附件，或把合同首页文字粘贴到输入框')
      return
    }
    setAiLoading(true)
    try {
      const r = await autofillRdweb(src)
      if (!r.data.ok) throw new Error(r.data.error || '识别失败')
      form.setFieldsValue(r.data.data)
      const empty = fields.filter(f => f.required && !r.data.data[f.key]).map(f => f.key)
      if (empty.length) {
        message.warning(`已填写 ${r.data.filled} 项，以下字段未识别到，请手工补充：${empty.join('、')}`)
      } else {
        message.success(`已自动填写 ${r.data.filled} 项，请核对后提交`)
      }
    } catch (e: any) {
      message.error(e?.response?.data?.error || e?.message || 'AI 识别失败')
    } finally {
      setAiLoading(false)
    }
  }

  // ── 附件上传（支持多个）─────────────────────────────────────────
  const doUpload = async (file: File) => {
    setUploading(true)
    try {
      const r = await uploadRdwebFile(file)
      if (!r.data.ok) throw new Error(r.data.error || '上传失败')
      const uid = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
      setAttachments(prev => [...prev, { uid, path: r.data.path, name: r.data.name }])
      setAiUid(prev => prev || uid)   // 首个附件默认作为 AI 识别对象
      message.success(`附件已上传：${r.data.name}`)
    } catch (e: any) {
      message.error(e?.response?.data?.error || e?.message || '上传失败')
    } finally {
      setUploading(false)
    }
    return false // 阻止 antd 默认上传
  }

  const removeAtt = (uid: string) => {
    setAttachments(prev => prev.filter(a => a.uid !== uid))
    setAiUid(prev => (prev === uid ? (attachments.find(a => a.uid !== uid)?.uid || '') : prev))
  }

  const aiAtt = attachments.find(a => a.uid === aiUid)

  // ── 提交 ─────────────────────────────────────────────────────
  const doSubmit = async () => {
    const values = await form.validateFields()
    if (!attachments.length) {
      message.warning('rd-web 审签单要求必须上传合同附件，请先上传')
      return
    }
    const acctTip = account?.configured
      ? `将使用你的 rd-web 账号（${account.phone_masked}）推送。`
      : '你尚未配置个人 rd-web 账号，将回退使用公用账号推送。'
    Modal.confirm({
      title: '确认推送到 rd-web 合同审签单？',
      content: `合同：${values['合同名称'] || ''}，附件 ${attachments.length} 个（${attachments.map(a => a.name).join('、')}）。${acctTip}提交后由后台自动填报，请勿重复提交。`,
      okText: '确认推送',
      cancelText: '再检查一下',
      onOk: async () => {
        setSubmitting(true)
        try {
          const r = await submitRdweb(values, attachments.map(a => ({ path: a.path, name: a.name })))
          if (!r.data.ok) throw new Error(r.data.error || '提交失败')
          message.info('任务已提交，正在后台自动填报…')
          startPolling()
        } catch (e: any) {
          setSubmitting(false)
          message.error(e?.response?.data?.error || e?.message || '提交失败')
        }
      },
    })
  }

  // ── 保存我的 rd-web 账号 ────────────────────────────────────────
  const saveAccount = async () => {
    const v = await acctForm.validateFields()
    try {
      const r = await saveRdwebMyAccount(v.phone, v.password)
      if (!r.data.ok) throw new Error(r.data.error || '保存失败')
      message.success('已保存，本人后续推送将使用该账号')
      setAcctOpen(false)
      acctForm.resetFields()
      reloadAccount()
    } catch (e: any) {
      message.error(e?.response?.data?.error || e?.message || '保存失败')
    }
  }

  const running = !!status?.running || submitting

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <Title level={3}><ThunderboltOutlined /> 合同审签推送</Title>
      <Paragraph type="secondary">
        把合同直接推送到 rd-web 合同审签单。可先粘贴合同首页文字，由 AI 自动填写字段，核对后上传附件提交。
      </Paragraph>

      {status && !status.running && status.ok !== null && (
        <Alert
          style={{ marginBottom: 14 }}
          type={status.ok ? 'success' : 'error'}
          showIcon
          message={status.ok
            ? `上次推送成功${status.serial_no ? `，流水号：${status.serial_no}` : ''}`
            : `上次推送失败：${status.msg || '未知原因'}`}
        />
      )}
      {running && (
        <Alert style={{ marginBottom: 14 }} type="info" showIcon
          message="正在后台自动填报 rd-web 审签单，请稍候…（页面会自动刷新结果）" />
      )}

      {account && (
        <Alert
          style={{ marginBottom: 14 }}
          type={account.configured ? 'success' : 'warning'}
          showIcon
          message={account.configured
            ? `本次将使用你的 rd-web 账号（${account.phone_masked}）推送`
            : '你尚未配置个人 rd-web 账号，推送将回退使用公用账号——建议配置为自己的账号'}
          action={
            <Button size="small" icon={<KeyOutlined />}
              onClick={() => { acctForm.resetFields(); setAcctOpen(true) }}>
              {account.configured ? '修改账号' : '配置我的账号'}
            </Button>
          }
        />
      )}

      <Row gutter={14}>
        <Col xs={24} md={9}>
          <Card size="small" title="① 上传合同附件（必传，可多个）" style={{ marginBottom: 14 }}>
            <Upload.Dragger
              multiple
              showUploadList={false}
              beforeUpload={f => doUpload(f as File)}
              disabled={uploading}
            >
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p className="ant-upload-text">点击或拖拽上传合同文件（支持多选，全部随单提交）</p>
              <p className="ant-upload-hint">docx / doc / pdf / 图片（扫描件自动走 OCR）/ 压缩包</p>
            </Upload.Dragger>

            {attachments.length > 0 && (
              <>
                <div style={{ margin: '10px 0 4px', fontSize: 12, color: '#888' }}>
                  已上传 {attachments.length} 个附件，勾选其中一个供 AI 读取：
                </div>
                <Radio.Group value={aiUid} onChange={e => setAiUid(e.target.value)} style={{ width: '100%' }}>
                  <List
                    size="small"
                    bordered
                    dataSource={attachments}
                    renderItem={a => (
                      <List.Item
                        actions={[
                          <Button key="d" type="text" size="small" danger
                            icon={<DeleteOutlined />} onClick={() => removeAtt(a.uid)} />,
                        ]}
                      >
                        <Radio value={a.uid}>
                          <Text style={{ fontSize: 13 }}>{a.name}</Text>
                        </Radio>
                      </List.Item>
                    )}
                  />
                </Radio.Group>
              </>
            )}

            <Button
              type="primary" block icon={<RobotOutlined />}
              style={{ marginTop: 10 }}
              disabled={!aiAtt}
              loading={aiLoading}
              onClick={() => aiAtt && doAutofill({ file_path: aiAtt.path })}
            >
              {aiAtt ? `AI 读取「${aiAtt.name}」并填写右侧表单` : 'AI 读取选中附件并填写'}
            </Button>
          </Card>

          <Card size="small" title={<span><RobotOutlined /> 或：粘贴合同文字识别</span>}>
            <Input.TextArea
              rows={8}
              value={pasteText}
              onChange={e => setPasteText(e.target.value)}
              placeholder={'附件读不出文字时的备选：把合同首页（含甲乙方信息、金额的部分）文字粘贴到这里，格式乱一点没关系。'}
            />
            <Button
              type="primary" ghost block icon={<RobotOutlined />}
              style={{ marginTop: 10 }}
              loading={aiLoading}
              onClick={() => doAutofill({ text: pasteText })}
            >
              AI 识别粘贴内容并填写
            </Button>
          </Card>
        </Col>

        <Col xs={24} md={15}>
          <Card size="small" title="② 审签单信息（提交前请逐项核对）">
            <Form form={form} layout="vertical"
              initialValues={{
                合同类别: '采购部合同', 经办人: '黄新博',
                合同甲方: '内江市第一人民医院', 甲方法定代表人: '谢晓阳',
                甲方联系电话: '0832-2256120',
                甲方地址: '四川省内江市市中区沱中路41号、汉安大道西段1866号',
              }}>
              <Row gutter={12}>
                {fields.map(f => (
                  <Col xs={24} sm={f.key.includes('地址') || f.key === '合同名称' || f.key === '项目名称及包号' ? 24 : 12}
                    key={f.key}>
                    <Form.Item
                      name={f.key}
                      label={f.key}
                      rules={f.required ? [{ required: true, message: `请填写${f.key}` }] : []}
                    >
                      {f.options
                        ? <Select options={f.options.map(o => ({ value: o, label: o }))} />
                        : <Input placeholder={f.hint} allowClear />}
                    </Form.Item>
                  </Col>
                ))}
              </Row>
            </Form>
            <Space>
              <Button type="primary" icon={<SendOutlined />}
                loading={running} onClick={doSubmit}>
                推送到 rd-web 审签
              </Button>
              <Button onClick={() => { form.resetFields(); setAttachments([]); setAiUid(''); setPasteText('') }}>
                清空重来
              </Button>
            </Space>
          </Card>
        </Col>
      </Row>

      <Card size="small" style={{ marginTop: 14 }}
        title={<span><HistoryOutlined /> 推送记录</span>}
        extra={<Button size="small" onClick={reloadRecords}>刷新</Button>}>
        <Table<RdwebPushRecord>
          rowKey="id"
          size="small"
          dataSource={records}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          columns={[
            { title: '提交时间', dataIndex: 'created_at', width: 150 },
            { title: '合同名称', dataIndex: 'contract_name', ellipsis: true },
            { title: '附件', dataIndex: 'file_name', width: 180, ellipsis: true },
            { title: '操作人', dataIndex: 'display_name', width: 90,
              render: (v, r) => v || r.username },
            { title: '结果', dataIndex: 'status', width: 90,
              render: (v: RdwebPushRecord['status']) => ({
                running:     <Tag color="processing">进行中</Tag>,
                ok:          <Tag color="green">成功</Tag>,
                fail:        <Tag color="red">失败</Tag>,
                interrupted: <Tag color="orange">已中断</Tag>,
              }[v]) },
            { title: '流水号', dataIndex: 'serial_no', width: 150,
              render: v => v ? <Text copyable>{v}</Text> : '—' },
            { title: '说明', dataIndex: 'msg', ellipsis: true,
              render: v => <Text type="secondary" style={{ fontSize: 12 }}>{v}</Text> },
          ]}
        />
      </Card>

      <Modal
        title="配置我的 rd-web 登录账号"
        open={acctOpen}
        onCancel={() => setAcctOpen(false)}
        onOk={saveAccount}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
        <Alert style={{ marginBottom: 12 }} type="info" showIcon
          message="每人用自己的 rd-web 账号推送，互不冲突。账号绑定到当前登录人，仅本人推送时使用。" />
        <Form form={acctForm} layout="vertical">
          <Form.Item name="phone" label="rd-web 登录手机号"
            rules={[{ required: true, message: '请填写登录手机号' }]}>
            <Input placeholder="如 13029144451" allowClear />
          </Form.Item>
          <Form.Item name="password" label="rd-web 登录密码"
            rules={[{ required: true, message: '请填写登录密码' }]}>
            <Input.Password placeholder="登录密码" autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
