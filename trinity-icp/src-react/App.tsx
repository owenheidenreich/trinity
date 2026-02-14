/**
 * App — root component.
 */
import { AppShell } from './components/layout/AppShell';
import { ToastProvider } from './components/notifications/ToastProvider';

export function App() {
  return (
    <>
      <AppShell />
      <ToastProvider />
    </>
  );
}

export default App;
