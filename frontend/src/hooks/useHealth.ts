import { useQuery } from '@tanstack/react-query'

import { healthQuery } from '@/lib/api'

/** Backend reachability. Used by the shell to show API status; also the phase-0
 *  proof that the full request path works end to end. */
export function useHealth() {
  return useQuery({
    ...healthQuery(),
    // A cold Render instance takes ~50s to wake, so retry rather than showing an
    // error on the first miss.
    retry: 2,
    staleTime: 30_000,
  })
}
