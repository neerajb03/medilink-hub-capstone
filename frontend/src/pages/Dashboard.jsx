import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import Navbar from '../components/Navbar'
import { userApi, apptApi, healthApi, documentApi } from '../api/axios'

function parseToken() {
  try {
    const token = localStorage.getItem('token')
    if (!token) return null
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload
  } catch { return null }
}

export default function Dashboard() {
  const [user, setUser] = useState(null)
  const [stats, setStats] = useState({ appointments: 0, records: 0, documents: 0 })
  const tokenData = parseToken()
  const role = tokenData?.role || ''

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [userRes, apptRes, recRes, docRes] = await Promise.allSettled([
          userApi.get('/me'),
          apptApi.get('/appointments'),
          healthApi.get('/records'),
          documentApi.get('/documents')
        ])

        if (userRes.status === 'fulfilled') setUser(userRes.value.data)
        setStats({
          appointments: apptRes.status === 'fulfilled' ? apptRes.value.data.length : 0,
          records: recRes.status === 'fulfilled' ? recRes.value.data.length : 0,
          documents: docRes.status === 'fulfilled' ? docRes.value.data.length : 0,
        })
      } catch (err) {
        console.error('Dashboard fetch error:', err)
      }
    }
    fetchData()
  }, [])

  return (
    <div className="app-layout">
      <Navbar />
      <main className="main-content">
        <div className="page-header">
          <h2>Welcome back{user ? `, ${user.name}` : ''} 👋</h2>
          <p>Here's an overview of your healthcare dashboard</p>
        </div>

        <div className="card-grid" style={{ marginBottom: '32px' }}>
          <Link to="/appointments" className="stat-card stat-card-link">
            <div className="stat-icon purple">📅</div>
            <div className="stat-info">
              <h3>{stats.appointments}</h3>
              <p>Appointments</p>
            </div>
          </Link>
          <Link to="/records" className="stat-card stat-card-link">
            <div className="stat-icon cyan">❤️</div>
            <div className="stat-info">
              <h3>{stats.records}</h3>
              <p>Health Records</p>
            </div>
          </Link>
          <Link to="/documents" className="stat-card stat-card-link">
            <div className="stat-icon green">📄</div>
            <div className="stat-info">
              <h3>{stats.documents}</h3>
              <p>Documents</p>
            </div>
          </Link>
          <div className="stat-card">
            <div className="stat-icon amber">🛡️</div>
            <div className="stat-info">
              <h3 style={{ textTransform: 'capitalize' }}>{user?.role || '—'}</h3>
              <p>Account Role</p>
            </div>
          </div>
        </div>

        <div className="card">
          <h3 style={{ marginBottom: '16px', fontWeight: 600 }}>Quick Actions</h3>
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            {role === 'patient' && (
              <Link to="/appointments" className="btn btn-primary btn-sm">📅 New Appointment</Link>
            )}
            {role === 'doctor' && (
              <Link to="/records" className="btn btn-primary btn-sm">❤️ Add Health Record</Link>
            )}
            <Link to="/records" className="btn btn-secondary btn-sm">❤️ View Records</Link>
            <Link to="/documents" className="btn btn-secondary btn-sm">📄 Upload Document</Link>
          </div>
        </div>
      </main>
    </div>
  )
}
