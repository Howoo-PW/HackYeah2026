import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

/**
 * Supabase client, used ONLY for login (contract/plan: data goes through the backend).
 * Needs the public publishable key; `null` when env vars are missing so the app still runs without auth.
 */
export const supabase = url && anonKey ? createClient(url, anonKey) : null
