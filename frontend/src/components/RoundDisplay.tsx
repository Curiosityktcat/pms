import { Input } from 'antd'
import { cnOrdinal } from '../utils/ordinal'

/**
 * 开标次数只读展示。第几次采购是流程算出来的（项目当前轮次），
 * 不该让人手选——原来是 1~5 的下拉，第六次根本选不到，还容易选错轮次。
 * 放在 Form.Item 里当受控组件用，值仍随表单提交。
 */
export default function RoundDisplay({ value }: { value?: number }) {
  return (
    <Input
      readOnly
      value={value ? `第${cnOrdinal(value)}次` : '—'}
      style={{ background: '#f5f5f5', color: '#262626', cursor: 'default' }}
    />
  )
}
