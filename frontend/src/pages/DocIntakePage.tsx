/**
 * 资料智能归档（工具）——同源反代内嵌 doc-intake 服务(9080)的拖拽上传界面。
 * 拖进合同/资料 → PaddleOCR → AI 判类型 → 自动归档留底。人和 agent 同一后端接口。
 */
export default function DocIntakePage() {
  return (
    <div style={{ height: 'calc(100vh - 118px)', background: 'var(--pms-surface, #fff)', borderRadius: 8, overflow: 'hidden' }}>
      <iframe
        src="/doc-intake-svc/"
        title="资料智能归档"
        style={{ width: '100%', height: '100%', border: 'none' }}
      />
    </div>
  )
}
