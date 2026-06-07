import { NavLink, useNavigate } from 'react-router-dom'

export default function Navbar() {
  const navigate = useNavigate()

  const handleLogout = () => {
    localStorage.removeItem('token')
    navigate('/login')
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <h1>MediLink Hub</h1>
        <span>Healthcare Platform</span>
      </div>
      <nav className="sidebar-nav">
        <NavLink to="/dashboard" className={({ isActive }) => isActive ? 'active' : ''}>
          <span className="nav-icon">📊</span>
          Dashboard
        </NavLink>
        <NavLink to="/appointments" className={({ isActive }) => isActive ? 'active' : ''}>
          <span className="nav-icon">📅</span>
          Appointments
        </NavLink>
        <NavLink to="/records" className={({ isActive }) => isActive ? 'active' : ''}>
          <span className="nav-icon">❤️</span>
          Health Records
        </NavLink>
        <NavLink to="/documents" className={({ isActive }) => isActive ? 'active' : ''}>
          <span className="nav-icon">📄</span>
          Documents
        </NavLink>
        <NavLink to="/chatbot" className={({ isActive }) => isActive ? 'active' : ''}>
          <span className="nav-icon">🤖</span>
          AI Assistant
        </NavLink>
      </nav>
      <div className="sidebar-footer">
        <button onClick={handleLogout}>
          🚪 Sign Out
        </button>
      </div>
    </aside>
  )
}
