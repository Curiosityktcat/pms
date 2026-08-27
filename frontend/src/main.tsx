import { createRoot } from 'react-dom/client'
import './index.css'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import App from './App.tsx'

// 日期控件的月份/星期跟着 dayjs 的语言走：antd 配了 zhCN 也没用，
// dayjs 不加载中文包，日历面板还是 Jan/Mo Tu We，用的人看不懂。
dayjs.locale('zh-cn')

createRoot(document.getElementById('root')!).render(<App />)
