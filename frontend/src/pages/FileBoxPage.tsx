import { useState, useEffect, useCallback } from 'react'
import {
  Card, Table, Button, Space, Typography, App, Popconfirm, Upload, Progress,
  Tag, Breadcrumb, Modal, Input,
} from 'antd'
import {
  FolderOpenOutlined, FolderOutlined, FileOutlined, DownloadOutlined,
  DeleteOutlined, ReloadOutlined, UploadOutlined, FolderAddOutlined, HomeOutlined,
  EyeOutlined,
} from '@ant-design/icons'
import {
  listDir, uploadEntries, downloadFile, downloadFileNative, downloadFolderNative,
  previewUrl, mkdir, deletePath, joinPath, parentPath, NATIVE_DOWNLOAD_BYTES,
  type FileEntry, type TransferStat,
} from '../services/filebox'
import FilePreviewModal, { isPreviewable } from '../components/FilePreviewModal'

const { Title, Text } = Typography

interface Picked { uid: string; name: string; file: File; relpath: string }

function fmtSize(n: number | null) {
  if (n == null) return '—'
  if (n >= 1024 * 1024 * 1024) return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${n} B`
}

function fmtSpeed(bps: number) {
  if (!bps || bps <= 0) return '—'
  return `${fmtSize(bps)}/s`
}

function fmtEta(sec: number) {
  if (!sec || sec <= 0) return '—'
  if (sec >= 3600) return `${Math.floor(sec / 3600)}时${Math.floor((sec % 3600) / 60)}分`
  if (sec >= 60) return `${Math.floor(sec / 60)}分${Math.round(sec % 60)}秒`
  return `${Math.ceil(sec)}秒`
}

/** 传输状态条：百分比 + 速度 + 已传/总量 + 剩余时间 */
function TransferBar({ label, stat }: { label: string; stat: TransferStat | null }) {
  const pct = stat?.percent ?? 0
  return (
    <div style={{ width: '100%' }}>
      <Progress percent={pct} status={pct >= 100 ? 'success' : 'active'}
        format={p => (p && p >= 100 ? '完成，处理中…' : `${p}%`)} />
      <Text type="secondary" style={{ fontSize: 12 }}>
        {label}　🚀 {fmtSpeed(stat?.speedBps ?? 0)}
        {stat && stat.total > 0 && <>　{fmtSize(stat.loaded)} / {fmtSize(stat.total)}</>}
        　⏱ 剩余 {fmtEta(stat?.etaSec ?? 0)}
      </Text>
    </div>
  )
}

export default function FileBoxPage() {
  const { message } = App.useApp()
  const [cwd, setCwd] = useState('')           // 当前目录相对路径
  const [items, setItems] = useState<FileEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [picked, setPicked] = useState<Picked[]>([])
  const [uploading, setUploading] = useState(false)
  const [upStat, setUpStat] = useState<TransferStat | null>(null)
  const [dl, setDl] = useState<{ name: string; stat: TransferStat | null } | null>(null)
  const [mkOpen, setMkOpen] = useState(false)
  const [mkName, setMkName] = useState('')
  const [preview, setPreview] = useState<{ open: boolean; url: string; name: string }>({ open: false, url: '', name: '' })

  const load = useCallback(async (path: string) => {
    setLoading(true)
    try {
      const res = await listDir(path)
      setCwd(res.data.data.path)
      setItems(res.data.data.items || [])
    } catch { message.error('加载目录失败') } finally { setLoading(false) }
  }, [message])
  useEffect(() => { load('') }, [load])

  const enter = (name: string) => load(joinPath(cwd, name))
  const goUp = () => load(parentPath(cwd))

  const doUpload = async () => {
    if (!picked.length) { message.warning('请先选择文件'); return }
    setUploading(true); setUpStat(null)
    try {
      const res = await uploadEntries(cwd, picked.map(p => ({ file: p.file, relpath: p.relpath })), setUpStat)
      message.success(res.data.message || '上传成功')
      setPicked([]); load(cwd)
    } catch (err: unknown) {
      const m = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(m || '上传失败')
    } finally { setUploading(false); setUpStat(null) }
  }

  const doDownload = async (name: string, size: number | null) => {
    // 大文件不走 blob：整份读进标签页内存会卡死/OOM，交给浏览器下载器落盘
    if ((size ?? 0) > NATIVE_DOWNLOAD_BYTES) {
      downloadFileNative(joinPath(cwd, name))
      message.info('大文件已交给浏览器下载，请看浏览器的下载列表')
      return
    }
    setDl({ name, stat: null })
    try {
      await downloadFile(joinPath(cwd, name), name, (s) => setDl({ name, stat: s }))
    } catch {
      message.error('下载失败')
    } finally { setDl(null) }
  }

  // 文件夹打包体积事先未知（可能上 GB），一律走浏览器下载器；
  // 后端要先打完 zip 才有第一个字节，浏览器会显示为「等待中」，属正常。
  const doDownloadFolder = (name: string) => {
    downloadFolderNative(joinPath(cwd, name))
    message.info('正在服务器打包 zip，打包完成后浏览器会自动开始下载')
  }

  const openPreview = (name: string) =>
    setPreview({ open: true, url: previewUrl(joinPath(cwd, name)), name })

  const doMkdir = async () => {
    if (!mkName.trim()) { message.warning('请输入文件夹名'); return }
    try {
      await mkdir(cwd, mkName.trim())
      message.success('已新建文件夹'); setMkOpen(false); setMkName(''); load(cwd)
    } catch (err: unknown) {
      const m = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(m || '新建失败')
    }
  }

  const doDelete = async (e: FileEntry) => {
    try {
      await deletePath(joinPath(cwd, e.name))
      message.success('已删除'); load(cwd)
    } catch { message.error('删除失败') }
  }

  // 面包屑：根 + 各级目录
  const parts = cwd ? cwd.split('/') : []
  const crumbItems = [
    { title: <a onClick={() => load('')}><HomeOutlined /> 根目录</a> },
    ...parts.map((seg, i) => ({
      title: i === parts.length - 1
        ? seg
        : <a onClick={() => load(parts.slice(0, i + 1).join('/'))}>{seg}</a>,
    })),
  ]

  const columns = [
    {
      title: '名称', dataIndex: 'name', ellipsis: true,
      render: (v: string, r: FileEntry) => r.type === 'dir'
        ? <a onClick={() => enter(v)}><FolderOutlined style={{ color: '#faad14' }} /> {v}</a>
        : isPreviewable(v)
          ? <a onClick={() => openPreview(v)}><FileOutlined style={{ color: '#888' }} /> {v}</a>
          : <span><FileOutlined style={{ color: '#888' }} /> {v}</span>,
    },
    { title: '大小', dataIndex: 'size', width: 110, render: (n: number | null) => fmtSize(n) },
    { title: '修改时间', dataIndex: 'modified', width: 175,
      render: (v: string) => v?.replace('T', ' ') || '—' },
    {
      title: '操作', width: 150,
      render: (_: unknown, r: FileEntry) => (
        <Space size={4}>
          {r.type === 'file' && isPreviewable(r.name) && (
            <Button size="small" icon={<EyeOutlined />}
              onClick={() => openPreview(r.name)}>预览</Button>
          )}
          {r.type === 'file' && (
            <Button size="small" type="primary" ghost icon={<DownloadOutlined />}
              loading={dl?.name === r.name} disabled={!!dl}
              onClick={() => doDownload(r.name, r.size)}>下载</Button>
          )}
          {r.type === 'dir' && (
            <Button size="small" type="primary" ghost icon={<DownloadOutlined />}
              onClick={() => doDownloadFolder(r.name)}>下载(zip)</Button>
          )}
          <Popconfirm
            title={r.type === 'dir' ? `删除文件夹「${r.name}」及其全部内容？` : `删除「${r.name}」？`}
            okText="删除" okButtonProps={{ danger: true }} cancelText="取消"
            onConfirm={() => doDelete(r)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <FolderOpenOutlined /> 我的文件库
          </Title>
          <Text type="secondary">私人文件存储（根目录 ~/files），仅本人可见。上传/下载/管理电脑文件。</Text>
        </div>

        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={() => load(cwd)}>刷新</Button>
          <Button disabled={!cwd} onClick={goUp}>↑ 上一级</Button>
          <Button icon={<FolderAddOutlined />} onClick={() => { setMkName(''); setMkOpen(true) }}>新建文件夹</Button>
          <Upload multiple showUploadList={false}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            beforeUpload={(file: any) => {
              setPicked(prev => [...prev, { uid: file.uid, name: file.name, file, relpath: file.name }])
              return false
            }}>
            <Button icon={<UploadOutlined />}>选择文件</Button>
          </Upload>
          <Upload multiple directory showUploadList={false}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            beforeUpload={(file: any) => {
              const rel = file.webkitRelativePath || file.originFileObj?.webkitRelativePath || file.name
              setPicked(prev => [...prev, { uid: file.uid, name: rel, file, relpath: rel }])
              return false
            }}>
            <Button icon={<FolderOpenOutlined />}>选择文件夹</Button>
          </Upload>
        </Space>

        <Breadcrumb items={crumbItems} />

        {dl && (
          <Card size="small" style={{ background: '#f8f9fa' }}>
            <TransferBar label={`下载「${dl.name}」`} stat={dl.stat} />
          </Card>
        )}

        {picked.length > 0 && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Space wrap>
              <Text type="secondary">待上传到「{cwd || '根目录'}」：</Text>
              {picked.slice(0, 12).map(p => (
                <Tag key={p.uid} closable
                  onClose={() => setPicked(prev => prev.filter(x => x.uid !== p.uid))}>
                  {p.name}
                </Tag>
              ))}
              {picked.length > 12 && <Text type="secondary">…等共 {picked.length} 项</Text>}
            </Space>
            {uploading && <TransferBar label="上传中" stat={upStat} />}
            <Space>
              <Button type="primary" loading={uploading} onClick={doUpload}>
                上传 {picked.length} 个文件
              </Button>
              <Button onClick={() => setPicked([])} disabled={uploading}>清空</Button>
            </Space>
          </Space>
        )}

        <Table rowKey="name" size="small" loading={loading}
          columns={columns} dataSource={items}
          pagination={{ pageSize: 20, showTotal: t => `共 ${t} 项` }}
          locale={{ emptyText: '空文件夹' }} />
      </Space>

      <Modal title="新建文件夹" open={mkOpen} onOk={doMkdir}
        onCancel={() => setMkOpen(false)} okText="创建" destroyOnHidden>
        <Input placeholder="文件夹名" value={mkName} maxLength={100}
          onChange={e => setMkName(e.target.value)} onPressEnter={doMkdir}
          style={{ marginTop: 8 }} />
      </Modal>

      <FilePreviewModal
        open={preview.open}
        url={preview.url}
        filename={preview.name}
        onClose={() => setPreview(p => ({ ...p, open: false }))}
      />
    </Card>
  )
}
