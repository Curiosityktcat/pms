import { useState, useEffect, useCallback } from 'react'
import {
  Card, Upload, Button, Space, Tag, Typography, Input, App, Spin, Empty,
  Radio, Alert, Dropdown,
} from 'antd'
import {
  InboxOutlined, FileSearchOutlined, CopyOutlined, DownloadOutlined,
  ReloadOutlined, ClearOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'
import {
  ocrRecognize, ocrHealth, ocrExport,
  type OcrResult, type OcrEngine, type OcrExportFormat,
} from '../services/ocr'

const { Title, Text, Paragraph } = Typography
const { Dragger } = Upload

const ACCEPT = '.pdf,.png,.jpg,.jpeg,.bmp,.tiff,.webp'

export default function FileOcrPage() {
  const { message } = App.useApp()
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [recognizing, setRecognizing] = useState(false)
  const [result, setResult] = useState<OcrResult | null>(null)
  const [online, setOnline] = useState<boolean | null>(null)
  const [server, setServer] = useState('')
  const [engine, setEngine] = useState<OcrEngine>('classic')

  const checkHealth = useCallback(() => {
    setOnline(null)
    ocrHealth()
      .then(res => {
        setOnline(res.data.data.online)
        setServer(res.data.data.server || '')
      })
      .catch(() => setOnline(false))
  }, [])
  useEffect(() => { checkHealth() }, [checkHealth])

  const selectedFile = (fileList[0]?.originFileObj as File | undefined) || undefined

  const doRecognize = async () => {
    if (!selectedFile) {
      message.warning('请先选择要识别的文件')
      return
    }
    setRecognizing(true)
    setResult(null)
    try {
      const res = await ocrRecognize(selectedFile, engine)
      if (res.data.ok) {
        setResult(res.data.data)
        const d = res.data.data
        if (d.usage) {
          message.success(`识别完成，本次消耗 ${d.usage.total_tokens} token`
            + (d.cost != null ? `（约 ${d.cost} 元）` : ''))
        } else {
          message.success('识别完成')
        }
      } else {
        message.error(res.data.error || '识别失败')
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err?.response?.data?.error || '识别失败，请检查识别服务是否在线')
    } finally {
      setRecognizing(false)
    }
  }

  const clearAll = () => {
    setFileList([])
    setResult(null)
  }

  const copyMarkdown = async () => {
    if (!result?.markdown) return
    try {
      await navigator.clipboard.writeText(result.markdown)
      message.success('已复制到剪贴板')
    } catch {
      message.error('复制失败，请手动选择文本复制')
    }
  }

  const [exporting, setExporting] = useState(false)

  const saveBlob = (blob: Blob, name: string) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.click()
    URL.revokeObjectURL(url)
  }

  const downloadMarkdown = () => {
    if (!result) return
    const base = (result.filename || 'ocr').replace(/\.[^.]+$/, '')
    saveBlob(new Blob([result.markdown], { type: 'text/markdown;charset=utf-8' }), `${base}.md`)
  }

  const downloadAs = async (fmt: OcrExportFormat) => {
    if (!result?.markdown) return
    const base = (result.filename || 'ocr').replace(/\.[^.]+$/, '')
    setExporting(true)
    try {
      const res = await ocrExport(result.markdown, fmt, base)
      saveBlob(res.data as Blob, `${base}.${fmt}`)
      message.success(`已导出 ${fmt.toUpperCase()}`)
    } catch {
      message.error('导出失败，请稍后重试')
    } finally {
      setExporting(false)
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card>
        <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
          <Title level={4} style={{ margin: 0 }}>
            <FileSearchOutlined /> 文件识别
          </Title>
          <Space>
            {online === null && <Tag icon={<Spin size="small" />}>检测中</Tag>}
            {online === true && <Tag color="success">识别服务在线</Tag>}
            {online === false && <Tag color="error">识别服务离线</Tag>}
            <Button size="small" icon={<ReloadOutlined />} onClick={checkHealth}>
              重新检测
            </Button>
          </Space>
        </Space>
        <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
          上传 PDF 或图片（身份证、扫描件、合同等），自动识别为可复制的文本（Markdown）。
          {server && <Text type="secondary"> 识别服务：{server}</Text>}
        </Paragraph>
      </Card>

      <Card title="选择文件">
        <Space direction="vertical" style={{ width: '100%', marginBottom: 16 }}>
          <Radio.Group
            value={engine}
            onChange={(e) => setEngine(e.target.value as OcrEngine)}
            disabled={recognizing}
          >
            <Radio.Button value="classic">传统 OCR（免费）</Radio.Button>
            <Radio.Button value="paddle">PaddleOCR-VL 大模型（按 token 计费）</Radio.Button>
          </Radio.Group>
          {engine === 'paddle' ? (
            <Alert
              type="warning"
              showIcon
              message="大模型识别按 token 计费，价格较贵"
              description="按系统 AI 定价从余额扣费，页数越多消耗越大。复杂版式、表格、手写、印章等效果显著更好；清晰打印件建议优先用免费的传统 OCR。"
            />
          ) : (
            <Alert
              type="info"
              showIcon
              message="传统 OCR 免费、速度快，适合清晰的打印文件；复杂版式或手写件请切换大模型识别。"
            />
          )}
        </Space>
        <Dragger
          accept={ACCEPT}
          maxCount={1}
          fileList={fileList}
          beforeUpload={(file) => {
            setFileList([{
              uid: String(Date.now()),
              name: file.name,
              status: 'done',
              originFileObj: file as unknown as UploadFile['originFileObj'],
            }])
            setResult(null)
            return false // 阻止自动上传，改为点「开始识别」手动触发
          }}
          onRemove={() => { clearAll(); return true }}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">点击或拖拽文件到此处</p>
          <p className="ant-upload-hint">支持 PDF / PNG / JPG / BMP / TIFF / WEBP，单个文件</p>
        </Dragger>
        <Space style={{ marginTop: 16 }}>
          <Button
            type="primary"
            icon={<FileSearchOutlined />}
            loading={recognizing}
            disabled={!selectedFile || online === false}
            onClick={doRecognize}
          >
            开始识别
          </Button>
          <Button icon={<ClearOutlined />} onClick={clearAll} disabled={recognizing}>
            清空
          </Button>
        </Space>
      </Card>

      <Card
        title={
          <Space>
            识别结果
            {result?.pages != null && <Tag color="blue">{result.pages} 页</Tag>}
            {result?.engine === 'paddle' && <Tag color="purple">大模型</Tag>}
            {result?.engine === 'classic' && <Tag>传统 OCR</Tag>}
            {result?.usage && (
              <Tag color="orange">{result.usage.total_tokens} token
                {result.cost != null ? ` / 约${result.cost}元` : ''}</Tag>
            )}
            {result?.balance != null && <Tag color="gold">余额 {result.balance} 元</Tag>}
            {result?.filename && <Text type="secondary">{result.filename}</Text>}
          </Space>
        }
        extra={
          result && (
            <Space>
              <Button size="small" icon={<CopyOutlined />} onClick={copyMarkdown}>
                复制
              </Button>
              <Dropdown
                menu={{
                  items: [
                    { key: 'docx', label: '导出 Word (.docx)' },
                    { key: 'xlsx', label: '导出 Excel (.xlsx)' },
                    { key: 'pdf', label: '导出 PDF (.pdf)' },
                    { type: 'divider' },
                    { key: 'md', label: '下载 Markdown (.md)' },
                  ],
                  onClick: ({ key }) =>
                    key === 'md' ? downloadMarkdown() : downloadAs(key as OcrExportFormat),
                }}
              >
                <Button size="small" type="primary" ghost
                  icon={<DownloadOutlined />} loading={exporting}>
                  下载 / 导出
                </Button>
              </Dropdown>
            </Space>
          )
        }
      >
        <Spin spinning={recognizing} tip="识别中，页数较多时请耐心等待…">
          {result ? (
            <Input.TextArea
              value={result.markdown}
              onChange={(e) => setResult({ ...result, markdown: e.target.value })}
              autoSize={{ minRows: 12, maxRows: 30 }}
              style={{ fontFamily: 'monospace', fontSize: 13 }}
            />
          ) : (
            <Empty description={recognizing ? '识别中…' : '尚无识别结果'} />
          )}
        </Spin>
      </Card>
    </Space>
  )
}
