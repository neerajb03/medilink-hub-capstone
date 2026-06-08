import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import Navbar from '../components/Navbar'
import { apptApi, userApi } from '../api/axios'

function parseToken() {
  try {
    const token = localStorage.getItem('token')
    if (!token) return null
    return JSON.parse(atob(token.split('.')[1]))
  } catch { return null }
}

// --- Mini Calendar Component ---
function MiniCalendar({ selectedDate, onSelect }) {
  const today = new Date()
  const [viewMonth, setViewMonth] = useState(today.getMonth())
  const [viewYear, setViewYear] = useState(today.getFullYear())

  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate()
  const firstDayOfWeek = new Date(viewYear, viewMonth, 1).getDay()
  const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December']

  const prevMonth = () => {
    if (viewMonth === 0) { setViewMonth(11); setViewYear(y => y - 1) }
    else setViewMonth(m => m - 1)
  }

  const nextMonth = () => {
    if (viewMonth === 11) { setViewMonth(0); setViewYear(y => y + 1) }
    else setViewMonth(m => m + 1)
  }

  const isDisabled = (day) => {
    const d = new Date(viewYear, viewMonth, day)
    const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate())
    return d < todayStart
  }

  const isSelected = (day) => {
    if (!selectedDate) return false
    const d = new Date(viewYear, viewMonth, day)
    return d.toDateString() === selectedDate.toDateString()
  }

  const isToday = (day) => {
    return viewYear === today.getFullYear() &&
      viewMonth === today.getMonth() &&
      day === today.getDate()
  }

  const handleSelect = (day) => {
    if (isDisabled(day)) return
    const d = new Date(viewYear, viewMonth, day)
    onSelect(d)
  }

  // Can't navigate before current month
  const canGoPrev = viewYear > today.getFullYear() ||
    (viewYear === today.getFullYear() && viewMonth > today.getMonth())

  const cells = []
  for (let i = 0; i < firstDayOfWeek; i++) cells.push(null)
  for (let d = 1; d <= daysInMonth; d++) cells.push(d)

  return (
    <div className="mini-calendar">
      <div className="cal-header">
        <button type="button" className="cal-nav-btn" onClick={prevMonth} disabled={!canGoPrev}>‹</button>
        <span className="cal-title">{monthNames[viewMonth]} {viewYear}</span>
        <button type="button" className="cal-nav-btn" onClick={nextMonth}>›</button>
      </div>
      <div className="cal-day-names">
        {dayNames.map(d => <div key={d} className="cal-day-name">{d}</div>)}
      </div>
      <div className="cal-grid">
        {cells.map((day, i) => (
          <div
            key={i}
            className={[
              'cal-cell',
              day === null ? 'cal-empty' : '',
              day && isDisabled(day) ? 'cal-disabled' : '',
              day && isSelected(day) ? 'cal-selected' : '',
              day && isToday(day) ? 'cal-today' : '',
            ].filter(Boolean).join(' ')}
            onClick={() => day && handleSelect(day)}
          >
            {day}
          </div>
        ))}
      </div>
    </div>
  )
}


export default function Appointments() {
  const [appointments, setAppointments] = useState([])
  const [showModal, setShowModal] = useState(false)
  const [selectedDate, setSelectedDate] = useState(null)
  const [selectedTime, setSelectedTime] = useState('09:00')
  const [doctorId, setDoctorId] = useState('')
  const [doctors, setDoctors] = useState([])
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  const tokenData = parseToken()
  const role = tokenData?.role || ''
  const navigate = useNavigate()

  const fetchAppointments = async () => {
    try {
      const res = await apptApi.get('/appointments')
      setAppointments(res.data)
    } catch (err) {
      console.error('Fetch appointments error:', err)
    }
  }

  const fetchDoctors = async () => {
    try {
      const res = await userApi.get('/doctors')
      setDoctors(res.data)
    } catch (err) {
      console.error('Fetch doctors error:', err)
    }
  }

  useEffect(() => {
    fetchAppointments()
    if (role === 'patient') fetchDoctors()
  }, [])

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!selectedDate) {
      setError('Please select a date from the calendar')
      return
    }
    setError('')
    setSuccess('')
    setLoading(true)
    try {
      // Build ISO datetime from selected date + time
      const [hours, minutes] = selectedTime.split(':').map(Number)
      const dt = new Date(selectedDate)
      dt.setHours(hours, minutes, 0, 0)

      const payload = { 
        datetime: dt.toISOString(),
        patient_id: role === 'doctor' ? doctorId.trim() : tokenData.user_id,
        doctor_id: role === 'doctor' ? tokenData.user_id : doctorId.trim()
      }
      await apptApi.post('/appointments', payload)
      setSuccess('Appointment created successfully!')
      setShowModal(false)
      setSelectedDate(null)
      setSelectedTime('09:00')
      setDoctorId('')
      fetchAppointments()
    } catch (err) {
      const msg = err.response?.data?.detail?.error?.message || err.response?.data?.detail || 'Failed to create appointment'
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm('Cancel this appointment?')) return
    try {
      await apptApi.delete(`/appointments/${id}`)
      fetchAppointments()
    } catch (err) {
      const msg = err.response?.data?.detail?.error?.message || 'Failed to cancel'
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    }
  }

  const handleUpdateStatus = async (id, action) => {
    try {
      await apptApi.put(`/appointments/${id}/${action}`)
      fetchAppointments()
    } catch (err) {
      const msg = err.response?.data?.detail?.error?.message || err.response?.data?.detail || `Failed to ${action} appointment`
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    }
  }

  const getStatusClass = (status) => {
    switch (status) {
      case 'accepted': return 'badge-confirmed'
      case 'completed': return 'badge-confirmed'
      case 'denied': return 'badge-cancelled'
      case 'cancelled': return 'badge-cancelled'
      default: return 'badge-pending'
    }
  }

  const getStatusIcon = (status) => {
    switch (status) {
      case 'accepted': return '✅'
      case 'completed': return '✅'
      case 'denied': return '❌'
      case 'cancelled': return '❌'
      default: return '⏳'
    }
  }

  // Generate time slots from 08:00 to 20:00 in 30-min intervals
  const timeSlots = []
  for (let h = 8; h <= 20; h++) {
    for (let m = 0; m < 60; m += 30) {
      if (h === 20 && m > 0) break
      const hh = String(h).padStart(2, '0')
      const mm = String(m).padStart(2, '0')
      timeSlots.push(`${hh}:${mm}`)
    }
  }

  const formatTimeLabel = (t) => {
    const [h, m] = t.split(':').map(Number)
    const ampm = h >= 12 ? 'PM' : 'AM'
    const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h
    return `${h12}:${String(m).padStart(2, '0')} ${ampm}`
  }

  return (
    <div className="app-layout">
      <Navbar />
      <main className="main-content">
        <div className="page-header">
          <h2>Appointments</h2>
          <p>Manage your healthcare appointments</p>
        </div>

        {error && <div className="alert alert-error">{error}</div>}
        {success && <div className="alert alert-success">{success}</div>}

        <div className="section-header">
          <h3>All Appointments</h3>
          {role === 'patient' && (
            <button className="btn btn-primary btn-sm" onClick={() => setShowModal(true)}>
              + New Appointment
            </button>
          )}
        </div>

        {appointments.length === 0 ? (
          <div className="card">
            <div className="empty-state">
              <div className="empty-icon">📅</div>
              <h3>No appointments yet</h3>
              <p>{role === 'patient' ? 'Create your first appointment to get started' : 'No appointments to display'}</p>
            </div>
          </div>
        ) : (
          <div className="appointment-grid">
            {appointments.map((a) => {
              const apptDate = new Date(a.datetime)
              return (
                <div className="appointment-card" key={a.id}>
                  <div className="appt-card-date-strip">
                    <div className="appt-month">{apptDate.toLocaleDateString(undefined, { month: 'short' })}</div>
                    <div className="appt-day">{apptDate.getDate()}</div>
                    <div className="appt-year">{apptDate.getFullYear()}</div>
                  </div>
                  <div className="appt-card-body">
                    <div className="appt-time">
                      🕐 {apptDate.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                    </div>
                    <div className="appt-status">
                      <span className={`badge ${getStatusClass(a.status)}`}>
                        {getStatusIcon(a.status)} {a.status}
                      </span>
                    </div>
                    {a.doctor_id && (
                      <div className="appt-doctor">
                        <span className="appt-label">Doctor:</span> {doctors.find(d => d.id === a.doctor_id)?.name || a.doctor_id.slice(0, 8) + '…'}
                      </div>
                    )}
                  </div>
                  <div className="appt-card-actions">
                    {role === 'doctor' && a.status === 'pending' && (
                      <>
                        <button className="btn btn-primary btn-sm" onClick={() => handleUpdateStatus(a.id, 'accept')}>
                          Accept
                        </button>
                        <button className="btn btn-danger btn-sm" style={{marginLeft: '8px'}} onClick={() => handleUpdateStatus(a.id, 'deny')}>
                          Deny
                        </button>
                      </>
                    )}
                    {role === 'doctor' && a.status === 'accepted' && (
                      <button className="btn btn-primary btn-sm" onClick={() => handleUpdateStatus(a.id, 'complete')}>
                        Complete
                      </button>
                    )}
                    {role === 'doctor' && a.status === 'completed' && (
                      <button className="btn btn-primary btn-sm" onClick={() => navigate(`/records?appointment_id=${a.id}&patient_id=${a.patient_id}`)}>
                        Add Health Record
                      </button>
                    )}
                    {(role === 'patient' && a.status === 'pending') && (
                      <button className="btn btn-danger btn-sm" onClick={() => handleDelete(a.id)}>
                        Cancel
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {showModal && (
          <div className="modal-overlay" onClick={() => setShowModal(false)}>
            <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
              <h3>New Appointment</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '24px' }}>
                Select a date and time for your appointment
              </p>
              <form onSubmit={handleCreate}>
                <div className="appt-picker-layout">
                  <div className="appt-picker-calendar">
                    <label className="picker-label">Select Date</label>
                    <MiniCalendar selectedDate={selectedDate} onSelect={setSelectedDate} />
                  </div>
                  <div className="appt-picker-details">
                    <div className="form-group">
                      <label htmlFor="appt-time">Select Time</label>
                      <div className="time-grid">
                        {timeSlots.map(t => (
                          <button
                            key={t}
                            type="button"
                            className={`time-slot-btn ${selectedTime === t ? 'time-slot-active' : ''}`}
                            onClick={() => setSelectedTime(t)}
                          >
                            {formatTimeLabel(t)}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="form-group">
                      {role === 'patient' ? (
                        <>
                          <label htmlFor="appt-doctor">Select Doctor</label>
                          <select
                            id="appt-doctor"
                            value={doctorId}
                            onChange={(e) => setDoctorId(e.target.value)}
                            required
                          >
                            <option value="">— Choose a doctor —</option>
                            {doctors.map(d => (
                              <option key={d.id} value={d.id}>Dr. {d.name}</option>
                            ))}
                          </select>
                        </>
                      ) : (
                        <>
                          <label htmlFor="appt-doctor">Patient ID</label>
                          <input
                            id="appt-doctor"
                            type="text"
                            placeholder="UUID of patient"
                            value={doctorId}
                            onChange={(e) => setDoctorId(e.target.value)}
                            required
                          />
                        </>
                      )}
                    </div>

                    {selectedDate && (
                      <div className="appt-summary-box">
                        <div className="appt-summary-title">📅 Appointment Summary</div>
                        <div className="appt-summary-line">
                          <strong>Date:</strong> {selectedDate.toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                        </div>
                        <div className="appt-summary-line">
                          <strong>Time:</strong> {formatTimeLabel(selectedTime)}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                <div className="modal-actions">
                  <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>Cancel</button>
                  <button type="submit" className="btn btn-primary" disabled={loading || !selectedDate}>
                    {loading ? <span className="spinner"></span> : 'Create Appointment'}
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
