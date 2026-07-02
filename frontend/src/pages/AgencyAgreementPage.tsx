import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  Card, Button, Space, Tag, Input, Modal, Form, App, Typography,
  Upload, Select, List, Divider,
} from 'antd'
import {
  FileWordOutlined, SafetyCertificateOutlined, UploadOutlined,
  PaperClipOutlined, DeleteOutlined, FileAddOutlined,
} from '@ant-design/icons'
import { getProjects, type Project } from '../services/project'
import {
  generateAgencyAgreement,
  listAgencyAttachments, uploadAgencyAttachment,
  addAgencyAttachmentFromTemplate, deleteAgencyAttachment,
  type AgencyAttachment,
} from '../services/agencyAgreement'
import { listTemplates, type TemplateInfo } from '../services/template'
import RecordCards from '../components/RecordCards'
import HermesPanel, { type HermesField } from '../components/HermesPanel'
import ProjectListToolbar, { useProjectListFilter, PROJECT_ACCESSORS } from '../components/ProjectListToolbar'

const { Title, Text } = Typography

/** 把日期格式化为「2026年5月29日」 */
function todayCN() {
  const d = new Date()
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
}

export default function AgencyAgreementPage() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(true)
  const [projects, setProjects] = useState<Project[]>([])

  const [modalOpen, setModalOpen] = useState(false)
  const [current, setCurrent] = useState<Project | null>(null)
  const [generating, setGenerating] = useState(false)
  const [form] = Form.useForm()

  // rd-web 审签附件（自行上传 / 从模板库选用）
  const [attachments, setAttachments] = useState<AgencyAttachment[]>([])
  const [templates, setTemplates] = useState<TemplateInfo[]>([])
  const [tplKey, setTplKey] = useState<string>()
  const [attachBusy, setAttachBusy] = useState(false)

  const refreshAttachments = useCallback((pid: number) => {
    listAgencyAttachments(pid)
      .then(res => setAttachments(res.data.data || []))
      .catch(() => setAttachments([]))
  }, [])

  const load = useCallback(() => {
    setLoading(true)
    getProjects()
      .then(res => {
        // 仅「走代理」且非草稿的项目可生成委托代理协议
        const list = (res.data.data || []).filter(
          p => p.agency_code && !p.is_draft,
        )
        setProjects(list)
      })
      .catch(() => message.error('加载项目失败'))
      .finally(() => setLoading(false))
  }, [message])
  useEffect(() => { load() }, [load])

  const listFilter = useProjectListFilter(projects, PROJECT_ACCESSORS)
  const filtered = listFilter.filtered

  const openModal = (p: Project) => {
    setCurrent(p)
    form.setFieldsValue({
      agency_name: p.agency_name || '',
      agency_address: '',
      officer_name: p.officer || '',
      officer_phone: '0832-2256120',
      sign_date: todayCN(),
    })
    setModalOpen(true)
    refreshAttachments(p.id)
    if (!templates.length) {
      listTemplates().then(res => setTemplates(res.data.data || [])).catch(() => {})
    }
  }

  const doUploadAttachment = async (file: File) => {
    if (!current) return false
    setAttachBusy(true)
    try {
      const res = await uploadAgencyAttachment(current.id, file)
      setAttachments(res.data.data || [])
      message.success('附件已上传')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err?.response?.data?.error || '上传失败')
    } finally {
      setAttachBusy(false)
    }
    return false
  }

  const doAddTemplate = async () => {
    if (!current || !tplKey) return
    setAttachBusy(true)
    try {
      const res = await addAgencyAttachmentFromTemplate(current.id, tplKey)
      setAttachments(res.data.data || [])
      message.success('模板已加入附件')
      setTplKey(undefined)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err?.response?.data?.error || '加入失败')
    } finally {
      setAttachBusy(false)
    }
  }

  const doDeleteAttachment = async (name: string) => {
    if (!current) return
    try {
      const res = await deleteAgencyAttachment(current.id, name)
      setAttachments(res.data.data || [])
    } catch {
      message.error('删除失败')
    }
  }

  const handleGenerate = async () => {
    if (!current) return
    const values = await form.validateFields()
    setGenerating(true)
    try {
      const res = await generateAgencyAgreement(current.id, values)
      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `委托代理协议_${current.number || current.name}.docx`
      a.click()
      URL.revokeObjectURL(url)
      message.success('委托代理协议已生成，正在下载')
      setModalOpen(false)
    } catch (e: unknown) {
      const err = e as { response?: { data?: unknown } }
      message.error(
        err?.response?.data instanceof Blob
          ? '生成失败，请检查项目信息'
          : '生成失败',
      )
    } finally {
      setGenerating(false)
    }
  }

  const agencyFields = useMemo<HermesField[]>(() => current ? [
    { label: '合同名称',       value: `委托代理服务协议—${current.name || ''}`, long: true },
    { label: '合同编码',       value: `${current.number || ''}-代理-HT` },
    { label: '项目名称及包号', value: current.name || '', long: true },
    { label: '归口管理科室',   value: current.manage_dept || '' },
    { label: '合同金额',       value: '按协议约定' },
    { label: '合同甲方',       value: '内江市第一人民医院', readOnly: true },
    { label: '甲方法定代表人', value: '谢晓阳', readOnly: true },
    { label: '甲方联系电话',   value: '0832-2256120', readOnly: true },
    { label: '甲方地址',       value: '四川省内江市市中区沱中路41号、汉安大道西段1866号', readOnly: true, long: true },
    { label: '合同乙方',       value: current.agency_name || '' },
    { label: '乙方法定代表人', value: current.agency_legal_rep || '' },
    { label: '乙方联系电话',   value: current.agency_phone || '' },
    { label: '乙方地址',       value: current.agency_address || '', long: true },
    { label: '合同类别',       value: '采购部合同', readOnly: true },
    { label: '经办人',         value: current.officer || '' },
  ] : [], [current])

  return (
    <Card>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <SafetyCertificateOutlined /> 委托代理协议
          </Title>
          <Text type="secondary">
            选择走代理机构的项目，按模板一键生成《委托代理协议》Word 文档。
          </Text>
        </div>

        <ProjectListToolbar f={listFilter} />

        <RecordCards
          dataSource={filtered}
          loading={loading}
          emptyText="暂无可生成代理协议的项目"
          toCard={(r) => ({
            key: r.id,
            accent: '#1a73e8',
            title: r.name,
            subtitle: r.number || '无编号',
            statusText: r.status,
            statusColor: 'blue',
            tags: <Tag color="blue" style={{ marginInlineEnd: 0 }}>{r.agency_name || r.agency_code}</Tag>,
            fields: [
              { label: '经办人', value: r.officer },
            ],
            actions: (
              <Button type="primary" ghost size="small" icon={<FileWordOutlined />} onClick={() => openModal(r)}>
                生成代理协议
              </Button>
            ),
          })}
        />
      </Space>

      <Modal
        title={`生成委托代理协议${current ? ` — ${current.name}` : ''}`}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleGenerate}
        okText="生成并下载"
        confirmLoading={generating}
        destroyOnHidden
        width={560}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item
            label="代理机构全称（乙方）"
            name="agency_name"
            rules={[{ required: true, message: '请填写代理机构全称' }]}
          >
            <Input placeholder="如：四川中锦招标代理有限公司" />
          </Form.Item>
          <Form.Item label="代理机构地址" name="agency_address">
            <Input placeholder="选填，留空则协议中地址处空白" />
          </Form.Item>
          <Form.Item
            label="甲方指定经办人"
            name="officer_name"
            rules={[{ required: true, message: '请填写经办人' }]}
          >
            <Input placeholder="如：黄新博" />
          </Form.Item>
          <Form.Item label="经办人联系电话" name="officer_phone">
            <Input />
          </Form.Item>
          <Form.Item label="签订时间" name="sign_date">
            <Input placeholder="如：2026年5月29日" />
          </Form.Item>
        </Form>
        <Divider style={{ margin: '12px 0' }} />
        <div style={{ marginBottom: 4, fontWeight: 600 }}>
          <PaperClipOutlined /> rd-web 审签附件
          <Text type="secondary" style={{ fontWeight: 400, marginLeft: 8, fontSize: 12 }}>
            生成的协议 Word 自动作为第一个附件，以下附件随审签单一并提交
          </Text>
        </div>
        <Space wrap style={{ marginBottom: 8 }}>
          <Upload showUploadList={false} beforeUpload={doUploadAttachment}
            accept=".docx,.doc,.xlsx,.xls,.pdf,.jpg,.jpeg,.png,.zip">
            <Button size="small" icon={<UploadOutlined />} loading={attachBusy}>
              上传附件
            </Button>
          </Upload>
          <Select
            size="small" style={{ minWidth: 220 }} placeholder="从模板库选用…"
            value={tplKey} onChange={setTplKey} allowClear
            options={templates.filter(t => t.exists)
              .map(t => ({ value: t.key, label: `${t.label}（${t.filename}）` }))}
          />
          <Button size="small" icon={<FileAddOutlined />} disabled={!tplKey}
            loading={attachBusy} onClick={doAddTemplate}>
            加入附件
          </Button>
        </Space>
        {attachments.length > 0 && (
          <List
            size="small" bordered style={{ marginBottom: 8 }}
            dataSource={attachments}
            renderItem={item => (
              <List.Item
                actions={[
                  <Button key="del" type="text" size="small" danger
                    icon={<DeleteOutlined />}
                    onClick={() => doDeleteAttachment(item.name)} />,
                ]}
              >
                <PaperClipOutlined style={{ marginRight: 6 }} />{item.name}
                <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                  {(item.size / 1024).toFixed(0)} KB · {item.updated_at}
                </Text>
              </List.Item>
            )}
          />
        )}
        <div style={{ marginTop: 8 }}>
          <HermesPanel taskType="agency-agreement" projectId={current?.id}
            title={current?.name} fields={agencyFields}
            directSubmitUrl={current ? `/projects/${current.id}/agency-agreement/submit-to-rdweb` : undefined}
            directStatusUrl={current ? `/projects/${current.id}/agency-agreement/rdweb-status` : undefined} />
        </div>
      </Modal>
    </Card>
  )
}
