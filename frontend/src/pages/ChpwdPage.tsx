import { useState } from 'react'
import { Form, Input, Button, Card, App } from 'antd'
import { useNavigate } from 'react-router-dom'
import { authChpwd } from '../services/auth'

/**
 * embedded=true 用在「强制改密」那一屏：不套 Card、不给取消按钮、
 * 改完不跳转而是回调（那时候整个界面还被挡着，跳哪儿都没用）。
 */
export default function ChpwdPage(
  { embedded = false, onDone }: { embedded?: boolean; onDone?: () => void } = {},
) {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { message } = App.useApp()
  const [form] = Form.useForm()

  const onFinish = async (values: { old: string; n1: string; n2: string }) => {
    setLoading(true)
    try {
      await authChpwd(values.old, values.n1, values.n2)
      message.success('密码已修改')
      if (embedded) onDone?.()
      else navigate('/flow')
    } catch (err: any) {
      message.error(err.response?.data?.error || '修改失败')
    } finally {
      setLoading(false)
    }
  }

  const body = (
    <>
      <Form form={form} layout="vertical" onFinish={onFinish}>
        <Form.Item label="原密码" name="old" rules={[{ required: true, message: '请输入原密码' }]}>
          <Input.Password />
        </Form.Item>
        <Form.Item label="新密码" name="n1" rules={[
          { required: true, message: '请输入新密码' },
          { min: 8, message: '新密码至少 8 位' },
        ]}>
          <Input.Password />
        </Form.Item>
        <Form.Item
          label="确认新密码"
          name="n2"
          rules={[
            { required: true, message: '请再次输入新密码' },
            ({ getFieldValue }) => ({
              validator(_, val) {
                return !val || getFieldValue('n1') === val
                  ? Promise.resolve()
                  : Promise.reject('两次密码不一致')
              },
            }),
          ]}
        >
          <Input.Password />
        </Form.Item>
        <Form.Item style={{ marginBottom: 0 }}>
          <Button type="primary" htmlType="submit" loading={loading}
            block={embedded}>修改</Button>
          {!embedded && (
            <Button style={{ marginLeft: 8 }} onClick={() => navigate('/flow')}>取消</Button>
          )}
        </Form.Item>
      </Form>
    </>
  )

  if (embedded) return body
  return (
    <Card style={{ maxWidth: 420 }}>
      <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 20 }}>修改密码</div>
      {body}
    </Card>
  )
}
