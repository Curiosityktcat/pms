import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Card, Table, Row, Col, Statistic, Tag, Button, Space, Typography,
  Alert, Switch, Empty,
} from 'antd'
import {
  ReloadOutlined, DatabaseOutlined, CloudDownloadOutlined,
  ThunderboltOutlined, ApiOutlined,
} from '@ant-design/icons'
import {
  getPipeOverview,
  type PipeOverview, type ProvinceRow, type QueueRow,
  type ServiceRow, type WorkerRow, type LogRow,
} from '../services/datapipe'

const { Text, Title } = Typography

const fmt = (n: number) => (n || 0).toLocaleString('zh-CN')

/** 资产卡片的展示顺序与配色 */
const ASSET_ORDER: { key: string; color?: string; hint?: string }[] = [
  { key: '公告', color: '#1677ff' },
  { key: '项目', color: '#1677ff' },
  { key: '中标合同明细', color: '#52c41a', hint: '品牌/型号/单价' },
  { key: '采购需求文件', color: '#52c41a', hint: '技术参数来源' },
  { key: '设备技术参数', color: '#eb2f96', hint: 'Qwen 抽取' },
  { key: '已抽参数设备', color: '#eb2f96' },
  { key: '技术分行', color: '#fa8c16' },
  { key: '技术分达标', color: '#fa8c16', hint: '得分率≥95%' },
  { key: '联系人', color: '#722ed1' },
  { key: '联系人带手机', color: '#722ed1' },
  { key: 'UDI产品标识', color: '#13c2c2', hint: '药监局全量' },
  { key: 'UDI注册证', color: '#13c2c2' },
  { key: '附件已下载', color: '#8c8c8c' },
]

export default function DataPipeBoardPage() {
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<PipeOverview | null>(null)
  const [err, setErr] = useState('')
  const [auto, setAuto] = useState(true)
  const timer = useRef<number | null>(null)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const res = await getPipeOverview()
      if (res.data?.ok) {
        setData(res.data.data)
        setErr('')
      } else {
        setErr((res.data as any)?.error || '读取失败')
      }
    } catch (e: any) {
      setErr(e?.response?.data?.error || e?.message || '读取失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (timer.current) { window.clearInterval(timer.current); timer.current = null }
    if (auto) timer.current = window.setInterval(() => load(true), 30000)
    return () => { if (timer.current) window.clearInterval(timer.current) }
  }, [auto, load])

  const provCols = [
    { title: '省份', dataIndex: '省份', width: 90,
      render: (v: string) => <Text strong>{v}</Text> },
    { title: '已入库公告', dataIndex: '已入库', width: 120, align: 'right' as const,
      sorter: (a: ProvinceRow, b: ProvinceRow) => a.已入库 - b.已入库,
      render: (v: number) => fmt(v) },
    { title: '状态', dataIndex: '状态', width: 140,
      render: (_: string, r: ProvinceRow) =>
        r.未完成任务 > 0
          ? <Tag color="processing">抓取中 · 余 {r.未完成任务} 项</Tag>
          : <Tag color="success">已完成 · 日增量</Tag> },
    { title: '最近入库', dataIndex: '最近入库', width: 120,
      render: (v: string) => <Text type="secondary">{v || '—'}</Text> },
  ]

  const queueCols = [
    { title: '处理环节', dataIndex: '环节' },
    { title: '待办', dataIndex: '待办', align: 'right' as const,
      render: (v: number) =>
        v > 0 ? <Tag color={v > 10000 ? 'orange' : 'blue'}>{fmt(v)}</Tag>
              : <Tag color="success">已清空</Tag> },
  ]

  const logCols = [
    { title: '时间', dataIndex: '时间', width: 110 },
    { title: '阶段', dataIndex: '阶段', width: 80,
      render: (v: string) => <Tag>{v}</Tag> },
    { title: '内容', dataIndex: '内容', ellipsis: true },
  ]

  const svcOffline = (data?.服务 || []).filter(s => !s.在线)
  const workerDown = (data?.worker || []).filter(w => w.进程数 === 0)

  return (
    <div style={{ padding: 16 }}>
      <Row justify="space-between" align="middle" style={{ marginBottom: 12 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>
            <DatabaseOutlined /> 政采数据流水线看板
          </Title>
          <Text type="secondary">
            全国政府采购数据采集 · 器械参数挖掘 · 仅本人可见
            {data && <> · 更新于 {data.更新时间}</>}
          </Text>
        </Col>
        <Col>
          <Space>
            <Text type="secondary">自动刷新</Text>
            <Switch checked={auto} onChange={setAuto} size="small" />
            <Button icon={<ReloadOutlined />} loading={loading}
                    onClick={() => load()}>刷新</Button>
          </Space>
        </Col>
      </Row>

      {err && <Alert type="error" showIcon message={err} style={{ marginBottom: 12 }} />}

      {(svcOffline.length > 0 || workerDown.length > 0) && (
        <Alert
          type="warning" showIcon style={{ marginBottom: 12 }}
          message="有组件未在运行"
          description={
            <>
              {svcOffline.length > 0 && <div>离线服务：{svcOffline.map(s => `${s.名称}(${s.端口})`).join('、')}</div>}
              {workerDown.length > 0 && <div>未运行：{workerDown.map(w => w.名称).join('、')}</div>}
              <Text type="secondary">机器重启后需执行 ~/ccgp/ccgp_boot.sh 拉起</Text>
            </>
          }
        />
      )}

      {/* 数据资产 */}
      <Card size="small" title={<><DatabaseOutlined /> 数据资产</>}
            style={{ marginBottom: 12 }} loading={loading && !data}>
        <Row gutter={[12, 12]}>
          {ASSET_ORDER.map(({ key, color, hint }) => (
            <Col key={key} xs={12} sm={8} md={6} lg={4}>
              <Statistic
                title={<>{key}{hint && <Text type="secondary" style={{ fontSize: 11 }}> · {hint}</Text>}</>}
                value={data?.资产?.[key] ?? 0}
                formatter={(v) => fmt(Number(v))}
                valueStyle={{ color, fontSize: 20 }}
              />
            </Col>
          ))}
        </Row>
      </Card>

      <Row gutter={12}>
        {/* 抓取进度 */}
        <Col xs={24} lg={13}>
          <Card size="small" style={{ marginBottom: 12 }}
                title={<><CloudDownloadOutlined /> 各省抓取进度</>}
                extra={data && <Text type="secondary">近 1 小时入库 {fmt(data.小时吞吐)} 条</Text>}>
            <Table<ProvinceRow>
              size="small" rowKey="省份" pagination={false}
              loading={loading && !data}
              dataSource={data?.省份 || []} columns={provCols}
              locale={{ emptyText: <Empty description="暂无数据" /> }}
            />
          </Card>
        </Col>

        {/* 队列 + 服务 */}
        <Col xs={24} lg={11}>
          <Card size="small" style={{ marginBottom: 12 }}
                title={<><ThunderboltOutlined /> 处理队列</>}>
            <Table<QueueRow>
              size="small" rowKey="环节" pagination={false}
              loading={loading && !data}
              dataSource={data?.队列 || []} columns={queueCols}
            />
          </Card>

          <Card size="small" style={{ marginBottom: 12 }}
                title={<><ApiOutlined /> 服务与 worker</>}>
            <Space direction="vertical" style={{ width: '100%' }} size={4}>
              {(data?.服务 || []).map((s: ServiceRow) => (
                <Row key={s.端口} justify="space-between">
                  <Col><Text>{s.名称}</Text> <Text type="secondary">:{s.端口}</Text></Col>
                  <Col>{s.在线 ? <Tag color="success">在线</Tag> : <Tag color="error">离线</Tag>}</Col>
                </Row>
              ))}
              <div style={{ borderTop: '1px solid #f0f0f0', margin: '6px 0' }} />
              {(data?.worker || []).map((w: WorkerRow) => (
                <Row key={w.名称} justify="space-between">
                  <Col><Text>{w.名称}</Text></Col>
                  <Col>{w.进程数 > 0
                    ? <Tag color="success">{w.进程数} 个进程</Tag>
                    : <Tag color="error">未运行</Tag>}</Col>
                </Row>
              ))}
            </Space>
          </Card>
        </Col>
      </Row>

      {/* 活动日志 */}
      <Card size="small" title="最近活动">
        <Table<LogRow>
          size="small" rowKey={(_, i) => String(i)} pagination={false}
          loading={loading && !data}
          dataSource={data?.日志 || []} columns={logCols}
          locale={{ emptyText: <Empty description="暂无日志" /> }}
        />
      </Card>
    </div>
  )
}
