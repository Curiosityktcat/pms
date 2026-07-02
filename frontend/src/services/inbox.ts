import api from './api'

// ── Interfaces ──────────────────────────────────────────────────

export interface InboxSummary {
  pending_todos: number
  total: number
}

export interface InboxUser {
  username: string
  display_name: string
  role: string
}

export interface Todo {
  id: number
  owner: string
  owner_name: string
  title: string
  content: string
  status: '待办' | '已完成'
  priority: '普通' | '重要' | '紧急'
  due_date: string
  related_project_id: number | null
  related_project_name: string
  created_by: string
  created_by_name: string
  created_at: string
  done_at: string
  done_by: string
  source: 'manual' | 'system'
  source_key: string
}

// ── Summary / Users ─────────────────────────────────────────────

export const getInboxSummary = () =>
  api.get<{ ok: boolean; data: InboxSummary }>('/inbox/summary')

export const listInboxUsers = () =>
  api.get<{ ok: boolean; data: InboxUser[] }>('/inbox/users')

// ── Todos ───────────────────────────────────────────────────────

export const listTodos = (status: '待办' | '已完成' | 'all' = 'all') =>
  api.get<{ ok: boolean; data: Todo[] }>('/inbox/todos', { params: { status } })

export interface CreateTodoInput {
  title: string
  content?: string
  owner?: string
  priority?: '普通' | '重要' | '紧急'
  due_date?: string
  related_project_id?: number | null
  related_project_name?: string
}

export const createTodo = (data: CreateTodoInput) =>
  api.post<{ ok: boolean; data: Todo }>('/inbox/todos', data)

export const updateTodo = (id: number, data: Partial<CreateTodoInput>) =>
  api.put<{ ok: boolean; data: Todo }>(`/inbox/todos/${id}`, data)

export const doneTodo = (id: number) =>
  api.post<{ ok: boolean; data: Todo }>(`/inbox/todos/${id}/done`)

export const reopenTodo = (id: number) =>
  api.post<{ ok: boolean; data: Todo }>(`/inbox/todos/${id}/reopen`)

export const deleteTodo = (id: number) =>
  api.delete<{ ok: boolean; message: string }>(`/inbox/todos/${id}`)
