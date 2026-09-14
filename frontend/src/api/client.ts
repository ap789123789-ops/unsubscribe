import createClient from 'openapi-fetch'

import type { paths } from './generated/schema'

export const api = createClient<paths>({ baseUrl: window.location.origin })

export async function getHealth() {
  const { data, error } = await api.GET('/api/health')
  if (error || !data) throw new Error('Backend health check failed')
  return data
}

