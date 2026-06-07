import { useState, useEffect } from 'react'
import Navbar from '../components/Navbar'
import { documentApi } from '../api/axios'

export default function Documents() {
  const [documents, setDocuments] = useState([])
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [uploading, setUploading] = useState(false)
  const [dragover, setDragover] = useState(false)

  const fetchDocuments = async () => {
    try {
      const res = await documentApi.get('/documents')
      setDocuments(res.data)
    } catch (err) {
      console.error('Fetch documents error:', err)
    }
  }

  useEffect(() => {
    fetchDocuments()
  }, [])

  const handleUpload = async (file) => {
    if (!file) return
    setError('')
    setSuccess('')
    setUploading(true)

    try {
      // 1. Get presigned URL
      const { data } = await documentApi.post('/documents', {
        file_name: file.name,
        file_type: file.type || 'application/octet-stream',
        record_id: ''
      })
      const { upload_url, document_id } = data

      // 2. Upload directly to S3 (bypassing backend)
      const res = await fetch(upload_url, {
        method: 'PUT',
        headers: { 'Content-Type': file.type || 'application/octet-stream' },
        body: file
      })
      
      if (!res.ok) throw new Error('Failed to upload file to S3')

      // 3. Confirm upload
      await documentApi.post(`/documents/${document_id}/confirm`)

      setSuccess(`"${file.name}" uploaded successfully!`)
      fetchDocuments()
    } catch (err) {
      console.error(err)
      const msg = err.response?.data?.detail?.error?.message || err.response?.data?.detail || err.message || 'Upload failed'
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    } finally {
      setUploading(false)
    }
  }

  const handleFileChange = (e) => {
    handleUpload(e.target.files[0])
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragover(false)
    handleUpload(e.dataTransfer.files[0])
  }

  const handleView = async (id) => {
    try {
      const res = await documentApi.get(`/documents/${id}`)
      window.open(res.data.url, '_blank')
    } catch (err) {
      const msg = err.response?.data?.detail?.error?.message || 'Failed to get file URL'
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    }
  }

  const getFileIcon = (name) => {
    if (name.endsWith('.pdf')) return '📕'
    if (name.endsWith('.jpg') || name.endsWith('.jpeg')) return '🖼️'
    if (name.endsWith('.png')) return '🖼️'
    return '📄'
  }

  return (
    <div className="app-layout">
      <Navbar />
      <main className="main-content">
        <div className="page-header">
          <h2>Documents</h2>
          <p>Upload and manage your medical documents</p>
        </div>

        {error && <div className="alert alert-error">{error}</div>}
        {success && <div className="alert alert-success">{success}</div>}

        <div
          className={`upload-area ${dragover ? 'dragover' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragover(true) }}
          onDragLeave={() => setDragover(false)}
          onDrop={handleDrop}
          style={{ marginBottom: '32px' }}
        >
          <input
            type="file"
            accept=".pdf,.jpg,.jpeg,.png"
            onChange={handleFileChange}
            disabled={uploading}
          />
          <div className="upload-icon">
            {uploading ? '⏳' : '☁️'}
          </div>
          <h4>{uploading ? 'Uploading...' : 'Drop files here or click to browse'}</h4>
          <p>PDF, JPG, PNG — Max 5MB</p>
        </div>

        <div className="section-header">
          <h3>Uploaded Documents</h3>
        </div>

        {documents.length === 0 ? (
          <div className="card">
            <div className="empty-state">
              <div className="empty-icon">📄</div>
              <h3>No documents yet</h3>
              <p>Upload your first document above</p>
            </div>
          </div>
        ) : (
          <div className="doc-list">
            {documents.map((doc) => (
              <div className="doc-item" key={doc.id}>
                <div className="doc-item-info">
                  <div className="doc-item-icon">{getFileIcon(doc.file_name)}</div>
                  <div>
                    <div className="doc-item-name">{doc.file_name}</div>
                    <div className="doc-item-date">{new Date(doc.uploaded_at).toLocaleString()}</div>
                  </div>
                </div>
                <button className="btn btn-secondary btn-sm" onClick={() => handleView(doc.id)}>
                  View
                </button>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
