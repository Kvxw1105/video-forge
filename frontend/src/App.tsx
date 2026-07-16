import { BrowserRouter, Routes, Route } from 'react-router-dom'
import ErrorBoundary from './components/ui/ErrorBoundary'
import Home from './pages/Home'
import Editor from './pages/Editor'
import Library from './pages/Library'

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/editor/:id" element={<Editor />} />
          <Route path="/library" element={<Library />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
