import { useContext } from 'react'
import { AuthContext } from './authContext'

/** Current user and login actions. Must be used under {@link AuthProvider}. */
export function useAuth() {
  return useContext(AuthContext)
}
