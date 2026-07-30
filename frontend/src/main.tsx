import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from '@/App'
import '@/index.css'

/** 60s stale time per the operating rules: metric data is computed from monthly
 *  snapshots, so refetching more aggressively costs requests and changes nothing. */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
})

const container = document.getElementById('root')
if (!container) {
  throw new Error('#root is missing from index.html')
}

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
