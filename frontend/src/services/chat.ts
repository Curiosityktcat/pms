import api from './api'

export interface ChatContact {
  username: string
  display_name: string
  role: string
  unread: number
  last_text: string
  last_time: string
  last_id: number
}

export interface ChatMessage {
  id: number
  sender: string
  sender_name: string
  recipient: string
  recipient_name: string
  msg_type: 'text' | 'image' | 'file'
  text: string
  file_path: string
  file_name: string
  file_size: number
  is_read: number
  read_at: string
  created_at: string
}

export const getChatSummary = () =>
  api.get<{ ok: boolean; data: { unread: number } }>('/chat/summary')

export const listContacts = () =>
  api.get<{ ok: boolean; data: ChatContact[] }>('/chat/contacts')

export const getConversation = (peer: string) =>
  api.get<{ ok: boolean; data: ChatMessage[]; peer: { username: string; display_name: string } }>(
    '/chat/messages', { params: { peer } })

export const sendText = (recipient: string, text: string) =>
  api.post<{ ok: boolean; data: ChatMessage }>('/chat/messages', { recipient, text })

export const sendFileMessage = (recipient: string, file: File) => {
  const fd = new FormData()
  fd.append('recipient', recipient)
  fd.append('file', file)
  return api.post<{ ok: boolean; data: ChatMessage }>('/chat/messages/file', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const markConversationRead = (peer: string) =>
  api.post<{ ok: boolean; read: number }>('/chat/read', { peer })

export const chatFileUrl = (id: number, download = false) =>
  `/api/chat/files/${id}${download ? '?download=1' : ''}`
