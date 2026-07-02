import { useState, useEffect, useCallback } from 'react'
import { Card, Button, Space, Upload, App, Typography } from 'antd'
import { DownloadOutlined, UploadOutlined, FileWordOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd'
import {
  listTemplates, downloadTemplate, replaceTemplate, type TemplateInfo,
} from '../services/template'
import RecordCards from '../components/RecordCards'

const { Title, Text } = Typography

function fmtSize(n: number) {
  if (!n) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export default function TemplateManagePage() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<TemplateInfo[]>([])
  const [uploadingKey, setUploadingKey] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    listTemplates()
      .then(res => setData(res.data.data || []))
      .catch(() => message.error('加载模板列表失败'))
      .finally(() => setLoading(false))
  }, [message])
  useEffect(() => { load() }, [load])

  const handleDownload = async (t: TemplateInfo) => {
    try {
      const res = await downloadTemplate(t.key)
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = t.filename
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      message.error('下载失败')
    }
  }

  const makeUploadProps = (t: TemplateInfo): UploadProps => ({
    showUploadList: false,
    beforeUpload: async (file) => {
      setUploadingKey(t.key)
      try {
        await replaceTemplate(t.key, file as File)
        message.success(`已更新模板：${t.label}`)
        load()
      } catch (e: unknown) {
        const err = e as { response?: { data?: { error?: string } } }
        message.error(err?.response?.data?.error || '上传失败')
      } finally {
        setUploadingKey('')
      }
      return false // 阻止 antd 默认上传
    },
  })

  return (
    <Card>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>模板维护</Title>
          <Text type="secondary">
            管理各功能生成 Word 时所依赖的模板文件。替换前系统会自动备份原文件（.bak）。
            请保持模板中的占位符（如 XXXXX、202x年xx月xx日）不变，否则可能影响自动填充。
          </Text>
        </div>

        <RecordCards
          dataSource={data}
          loading={loading}
          emptyText="暂无模板"
          toCard={(t) => ({
            key: t.key,
            accent: t.exists ? '#34a853' : '#d93025',
            title: <Space><FileWordOutlined style={{ color: '#1a73e8' }} />{t.label}</Space>,
            subtitle: t.filename,
            statusText: t.exists ? '正常' : '缺失',
            statusColor: t.exists ? 'green' : 'red',
            fields: [
              { label: '大小', value: fmtSize(t.size) },
              { label: '更新时间', value: t.updated_at || '—' },
            ],
            actions: (
              <>
                <Button size="small" icon={<DownloadOutlined />} disabled={!t.exists} onClick={() => handleDownload(t)}>下载</Button>
                <Upload {...makeUploadProps(t)}>
                  <Button size="small" icon={<UploadOutlined />} loading={uploadingKey === t.key}>替换</Button>
                </Upload>
              </>
            ),
          })}
        />
      </Space>
    </Card>
  )
}
