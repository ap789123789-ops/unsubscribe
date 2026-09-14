import { Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from './AppShell'
import { ActivityPage } from '../features/activity/ActivityPage'
import { ConfirmationPage } from '../features/confirmation/ConfirmationPage'
import { ReviewRoute } from '../features/review/ReviewRoute'
import { ScanPage } from '../features/scan/ScanPage'
import { SettingsPage } from '../features/settings/SettingsPage'
import { SetupPage } from '../features/setup/SetupPage'

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/setup" replace />} />
        <Route path="setup" element={<SetupPage />} />
        <Route path="scan" element={<ScanPage />} />
        <Route path="review" element={<ReviewRoute />} />
        <Route path="confirm/:planId" element={<ConfirmationPage />} />
        <Route path="activity/:planId" element={<ActivityPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  )
}

