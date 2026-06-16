import { createBrowserRouter, RouterProvider } from 'react-router';
import { PlannerWorkspace } from './pages/PlannerWorkspace';

const router = createBrowserRouter([
  { path: '*', element: <PlannerWorkspace /> },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
