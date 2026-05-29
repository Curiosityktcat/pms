import { useState, useEffect, useMemo } from 'react'
import {
  Card, Table, Checkbox, Button, Space, App, Typography, Spin, Tag, Popconfirm,
} from 'antd'
import { SaveOutlined, ReloadOutlined, SafetyOutlined } from '@ant-design/icons'
import {
  getPermMatrix, setRolePerms, resetRolePerms,
  type PermGroup, type RoleInfo,
} from '../services/permission'

const { Title, Text } = Typography

interface Row {
  key: string
  label: string
  group: string
  isGroup?: boolean
}

export default function PermissionManagePage() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [catalog, setCatalog] = useState<PermGroup[]>([])
  const [roles, setRoles] = useState<RoleInfo[]>([])
  // 当前编辑中的权限：role -> Set(keys)
  const [perms, setPerms] = useState<Record<string, Set<string>>>({})
  // 原始权限（用于判断是否有改动）
  const [origin, setOrigin] = useState<Record<string, string[]>>({})

  const load = () => {
    setLoading(true)
    getPermMatrix()
      .then(res => {
        setCatalog(res.data.catalog)
        setRoles(res.data.roles)
        setOrigin(res.data.perms)
        const m: Record<string, Set<string>> = {}
        for (const r of res.data.roles) {
          m[r.role] = new Set(res.data.perms[r.role] || [])
        }
        setPerms(m)
      })
      .catch(() => message.error('加载权限矩阵失败（需 admin 账号）'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])  // eslint-disable-line react-hooks/exhaustive-deps

  // 行数据：每个分组一个表头行 + 各菜单项行
  const rows: Row[] = useMemo(() => {
    const out: Row[] = []
    for (const g of catalog) {
      out.push({ key: `__group__${g.group}`, label: g.group, group: g.group, isGroup: true })
      for (const it of g.items) {
        out.push({ key: it.key, label: it.label, group: g.group })
      }
    }
    return out
  }, [catalog])

  const toggle = (role: string, key: string, checked: boolean) => {
    setPerms(prev => {
      const next = new Set(prev[role])
      if (checked) next.add(key)
      else next.delete(key)
      return { ...prev, [role]: next }
    })
  }

  // 整组勾选/取消（某角色）
  const toggleGroup = (role: string, group: string, checked: boolean) => {
    const keys = catalog.find(g => g.group === group)?.items.map(i => i.key) || []
    setPerms(prev => {
      const next = new Set(prev[role])
      for (const k of keys) checked ? next.add(k) : next.delete(k)
      return { ...prev, [role]: next }
    })
  }

  const isDirty = (role: string) => {
    const cur = perms[role] || new Set()
    const orig = new Set(origin[role] || [])
    if (cur.size !== orig.size) return true
    for (const k of cur) if (!orig.has(k)) return true
    return false
  }
  const anyDirty = roles.some(r => isDirty(r.role))

  const handleSave = async () => {
    const dirtyRoles = roles.filter(r => isDirty(r.role))
    if (!dirtyRoles.length) { message.info('没有改动'); return }
    setSaving(true)
    try {
      for (const r of dirtyRoles) {
        await setRolePerms(r.role, Array.from(perms[r.role]))
      }
      message.success(`已保存 ${dirtyRoles.length} 个角色的权限`)
      load()
    } catch {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async (role: string) => {
    try {
      const res = await resetRolePerms(role)
      setPerms(prev => ({ ...prev, [role]: new Set(res.data.perms) }))
      setOrigin(prev => ({ ...prev, [role]: res.data.perms }))
      message.success('已恢复默认权限')
    } catch {
      message.error('恢复失败')
    }
  }

  const columns = [
    {
      title: '菜单 / 功能',
      dataIndex: 'label',
      key: 'label',
      fixed: 'left' as const,
      width: 220,
      render: (_: unknown, row: Row) =>
        row.isGroup
          ? <Text strong style={{ color: '#1677ff' }}>{row.label}</Text>
          : <span style={{ paddingLeft: 8 }}>{row.label}</span>,
    },
    ...roles.map((r: RoleInfo) => ({
      title: (
        <Space direction="vertical" size={0} style={{ textAlign: 'center' }}>
          <span>{r.role_cn}{isDirty(r.role) && <Tag color="orange" style={{ marginLeft: 4 }}>未保存</Tag>}</span>
          <Popconfirm title={`恢复「${r.role_cn}」的默认权限？`} onConfirm={() => handleReset(r.role)}>
            <Button type="link" size="small" icon={<ReloadOutlined />} style={{ fontSize: 12 }}>默认</Button>
          </Popconfirm>
        </Space>
      ),
      key: r.role,
      align: 'center' as const,
      width: 140,
      render: (_: unknown, row: Row) => {
        if (row.isGroup) {
          const keys = catalog.find(g => g.group === row.group)?.items.map(i => i.key) || []
          const cur = perms[r.role] || new Set()
          const all = keys.every(k => cur.has(k))
          const some = keys.some(k => cur.has(k))
          return (
            <Checkbox
              checked={all}
              indeterminate={!all && some}
              onChange={e => toggleGroup(r.role, row.group, e.target.checked)}
            />
          )
        }
        return (
          <Checkbox
            checked={perms[r.role]?.has(row.key) || false}
            onChange={e => toggle(r.role, row.key, e.target.checked)}
          />
        )
      },
    })),
  ]

  return (
    <Card>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }} align="start">
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <SafetyOutlined style={{ marginRight: 8 }} />权限管理
          </Title>
          <Text type="secondary">
            勾选各角色可访问的菜单。admin 账号始终拥有全部权限，无需配置。改动后点「保存」生效，用户重新登录后刷新。
          </Text>
        </div>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          loading={saving}
          disabled={!anyDirty}
          onClick={handleSave}
        >
          保存
        </Button>
      </Space>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
      ) : (
        <Table
          columns={columns}
          dataSource={rows}
          pagination={false}
          size="small"
          bordered
          scroll={{ x: 'max-content' }}
          rowClassName={(row: Row) => (row.isGroup ? 'perm-group-row' : '')}
        />
      )}
    </Card>
  )
}
