import { Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/AppShell'
import Acquisition from '@/pages/Acquisition'
import Ask from '@/pages/Ask'
import Engagement from '@/pages/Engagement'
import Overview from '@/pages/Overview'
import Productivity from '@/pages/Productivity'
import Retention from '@/pages/Retention'

/** Routes. Every page renders inside the shell, so the filter bar scopes all of them
 *  and the sidebar keeps the current slice when navigating. */
export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Overview />} />
        <Route path="acquisition" element={<Acquisition />} />
        <Route path="retention" element={<Retention />} />
        <Route path="engagement" element={<Engagement />} />
        <Route path="productivity" element={<Productivity />} />
        <Route path="ask" element={<Ask />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
