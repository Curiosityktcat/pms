import { useState, useEffect, useCallback } from 'react'
import {
  Card, Upload, Button, Space, Tag, Typography, Input, App, Spin, Empty,
} from 'antd'
import {
  InboxOutlined, FileSearchOutlined, CopyOutlined, DownloadOutlined,
  ReloadOutlined, ClearOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'
import { ocrRecognize, ocrHealth, type OcrResult } from '../services/ocr'

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
      const res = await ocrRecognize(selectedFile)
      if (res.data.ok) {
        setResult(res.data.data)
        message.success('识别完成')
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

  const downloadMarkdown = () => {
    if (!result) return
    const base = (result.filename || 'ocr').replace(/\.[^.]+$/, '')
    const blob = new Blob([result.markdown], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${base}.md`
    a.click()
    URL.revokeObjectURL(url)
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
            {result?.filename && <Text type="secondary">{result.filename}</Text>}
          </Space>
        }
        extra={
          result && (
            <Space>
              <Button size="small" icon={<CopyOutlined />} onClick={copyMarkdown}>
                复制
              </Button>
              <Button size="small" icon={<DownloadOutlined />} onClick={downloadMarkdown}>
                下载 .md
              </Button>
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
