import { useMutation } from '@tanstack/react-query'

import { apiPost, type AskResponse, type Envelope } from '@/lib/api'

/** The one mutation in the app.
 *
 * Everything else reads a metric and is a `useQuery`; asking a question sends something,
 * costs money, and must not fire on render or be retried automatically. `useMutation` is
 * the shape that says all three.
 *
 * No retry: a refusal is a considered answer, and a rate-limit failure only gets worse if
 * three tabs re-ask at once.
 */
export function useAsk() {
  return useMutation<Envelope<AskResponse>, unknown, string>({
    mutationFn: (question: string) => apiPost<AskResponse>('/api/ai/ask', { question }),
    retry: false,
  })
}
