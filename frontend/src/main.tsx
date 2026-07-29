import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'

import { BoardListPage } from './pages/BoardListPage'
import { BoardPage } from './pages/BoardPage'
import './styles.css'

const router = createBrowserRouter([
  { path: '/', element: <BoardListPage /> },
  { path: '/boards/:boardId', element: <BoardPage /> },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
