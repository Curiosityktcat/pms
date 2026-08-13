import api from './api'

export interface ProvinceRow {
  省份: string
  已入库: number
  未完成任务: number
  状态: string
  最近入库: string
}
export interface QueueRow { 环节: string; 待办: number }
export interface ServiceRow { 名称: string; 端口: number; 在线: boolean }
export interface WorkerRow { 名称: string; 进程数: number }
export interface LogRow { 时间: string; 阶段: string; 内容: string }

export interface PipeOverview {
  更新时间: string
  资产: Record<string, number>
  省份: ProvinceRow[]
  队列: QueueRow[]
  小时吞吐: number
  服务: ServiceRow[]
  worker: WorkerRow[]
  日志: LogRow[]
}

export const getPipeOverview = () =>
  api.get<{ ok: boolean; data: PipeOverview; cached: boolean }>('/datapipe/overview')
