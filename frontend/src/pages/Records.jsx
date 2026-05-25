import { useState, useEffect } from 'react'
import Navbar from '../components/Navbar'
import { healthApi, userApi } from '../api/axios'

function parseToken() {
  try {
    const token = localStorage.getItem('token')
    if (!token) return null
    return JSON.parse(atob(token.split('.')[1]))
  } catch { return null }
}

export default function Records() {
  const [records, setRecords] = useState([])
  const [showModal, setShowModal] = useState(false)
  const [patientEmail, setPatientEmail] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)
  const [patientLookupError, setPatientLookupError] = useState('')

  const tokenData = parseToken()
  const role = tokenData?.role || ''
  const isDoctor = role === 'doctor'

  const fetchRecords = async () => {
    try {
      const res = await healthApi.get('/records')
      setRecords(res.data)
    } catch (err) {
      console.error('Fetch records error:', err)
    }
  }

  useEffect(() => {
    fetchRecords()
  }, [])

  const handleCreate = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    setPatientLookupError('')
    setLoading(true)
    try {
      await healthApi.post('/records', {
        user_id: patientEmail,
        description
      })
      setSuccess('Record created successfully!')
      setShowModal(false)
      setPatientEmail('')
      setDescription('')
      fetchRecords()
    } catch (err) {
      const msg = err.response?.data?.detail?.error?.message || err.response?.data?.detail || 'Failed to create record'
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app-layout">
      <Navbar />
      <main className="main-content">
        <div className="page-header">
          <h2>Health Records</h2>
          <p>
            {isDoctor
              ? 'Create and manage patient health records'
              : 'View your health records created by your doctor'}
          </p>
        </div>

        {error && <div className="alert alert-error">{error}</div>}
        {success && <div className="alert alert-success">{success}</div>}

        <div className="section-header">
          <h3>All Records</h3>
          {isDoctor && (
            <button className="btn btn-primary btn-sm" onClick={() => setShowModal(true)}>
              + New Record
            </button>
          )}
        </div>

        {records.length === 0 ? (
          <div className="card">
            <div className="empty-state">
              <div className="empty-icon">❤️</div>
              <h3>No records yet</h3>
              <p>
                {isDoctor
                  ? 'Create a health record for a patient to get started'
                  : 'Health records will appear here when created by your doctor'}
              </p>
            </div>
          </div>
        ) : (
          <div className="records-grid">
            {records.map((r) => (
              <div className="record-card" key={r.id}>
                <div className="record-card-header">
                  <div className="record-card-icon">🩺</div>
                  <div className="record-card-date">
                    {new Date(r.created_at).toLocaleDateString(undefined, {
                      year: 'numeric', month: 'short', day: 'numeric'
                    })}
                  </div>
                </div>
                <div className="record-card-body">
                  <p className="record-description">{r.description}</p>
                </div>
                <div className="record-card-footer">
                  <span className="record-patient-label">Patient ID</span>
                  <span className="record-patient-id">{r.user_id.slice(0, 8)}…</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Only doctors can create records */}
        {showModal && isDoctor && (
          <div className="modal-overlay" onClick={() => setShowModal(false)}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <h3>New Health Record</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '24px' }}>
                Create a health record for a patient
              </p>
              <form onSubmit={handleCreate}>
                <div className="form-group">
                  <label htmlFor="rec-patient">Patient ID</label>
                  <input
                    id="rec-patient"
                    type="text"
                    placeholder="Enter patient UUID"
                    value={patientEmail}
                    onChange={(e) => setPatientEmail(e.target.value)}
                    required
                  />
                  {patientLookupError && (
                    <span style={{ color: 'var(--danger)', fontSize: '0.8rem', marginTop: '4px', display: 'block' }}>
                      {patientLookupError}
                    </span>
                  )}
                </div>
                <div className="form-group">
                  <label htmlFor="rec-desc">Description</label>
                  <textarea
                    id="rec-desc"
                    placeholder="Describe the diagnosis, treatment, or notes (max 1000 chars)"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    maxLength={1000}
                    required
                  />
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '4px', display: 'block' }}>
                    {description.length}/1000 characters
                  </span>
                </div>
                <div className="modal-actions">
                  <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>Cancel</button>
                  <button type="submit" className="btn btn-primary" disabled={loading}>
                    {loading ? <span className="spinner"></span> : 'Create Record'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
