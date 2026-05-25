import axios from 'axios'

const getToken = () => localStorage.getItem('token')

export const userApi = axios.create({ baseURL: import.meta.env.VITE_USER_URL })
export const apptApi = axios.create({ baseURL: import.meta.env.VITE_APPOINTMENT_URL })
export const healthApi = axios.create({ baseURL: import.meta.env.VITE_HEALTH_URL })
export const documentApi = axios.create({ baseURL: import.meta.env.VITE_DOCUMENT_URL })

const authInterceptor = config => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
}

userApi.interceptors.request.use(authInterceptor)
apptApi.interceptors.request.use(authInterceptor)
healthApi.interceptors.request.use(authInterceptor)
documentApi.interceptors.request.use(authInterceptor)
