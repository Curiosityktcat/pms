import { useEffect, useState } from 'react'
import { App, Button, Card, Table, Tag, Typography } from 'antd'
import { FilePdfOutlined } from '@ant-design/icons'
import {
  authzDocumentUrl, myAuthorizations, type AuthorizationInfo,
} from '../services/authorization'

const { Text, Title } = Typography
const STATE_COLOR: Record<string, string> = {
  生效: 'green', 已撤销: 'default', 未开始: 'blue', 已过期: 'orange', 授权人已换人: 'red',
}

export default function MyAuthorizationPage() {
  const { message } = App.useApp()
  const [rows, setRows] = useState<AuthorizationInfo[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    myAuthorizations().then(res => setRows(res.data.data))
      .catch(err => message.error(err?.response?.data?.error || '加载我的授权失败'))
      .finally(() => setLoading(false))
  }, [message])

  return <Card>
    <Title level={4} style={{ marginTop: 0 }}>我的授权</Title>
    <Text type="secondary">这里说明你的附加权限是谁授予、依据什么文件，以及何时到期；岗位基础权限不在此重复展示。</Text>
    <Table rowKey="id" style={{ marginTop: 16 }} loading={loading} dataSource={rows} columns={[
      { title: '来源', dataIndex: 'source', render: (v: string, r: AuthorizationInfo) => v === 'resolution' ? `医院决议${r.doc_no ? `（${r.doc_no}）` : ''}` : '科室负责人委托' },
      { title: '授权人', dataIndex: 'granter_name' },
      { title: '权限数量', dataIndex: 'perm_keys', render: (v: string[]) => `${v.length} 项` },
      { title: '有效期', render: (_: unknown, r: AuthorizationInfo) => `${r.valid_from} 至 ${r.valid_to}` },
      { title: '状态', dataIndex: 'effective_state', render: (v: string) => <Tag color={STATE_COLOR[v]}>{v}</Tag> },
      { title: '凭证', render: (_: unknown, r: AuthorizationInfo) => <Button type="link" icon={<FilePdfOutlined />} href={authzDocumentUrl(r.id)}>{r.doc_name}</Button> },
    ]} />
  </Card>
}
