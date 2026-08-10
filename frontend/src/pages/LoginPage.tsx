import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '../api'
import { useAuth } from '../auth'

export function LoginPage() {
  const { signedIn } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)

    try {
      signedIn(await api.login(email, password))
    } catch (cause) {
      // The back-end answers one message for every way a login can fail, so
      // there is nothing to translate here and nothing to add: repeating it is
      // the whole job.
      setError((cause as Error).message)
      setBusy(false)
      return
    }

    navigate('/', { replace: true })
  }

  return (
    <main className="page auth-page">
      <h1>Sign in</h1>

      {error && <p className="error">{error}</p>}

      <form className="auth-form" onSubmit={submit}>
        <label>
          Email
          <input
            type="email"
            name="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>

        <label>
          Password
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            required
            // No minLength here, unlike registration. A floor on this form would
            // refuse to submit a password that predates the rule, and the person
            // it locks out is the one who did nothing wrong.
            maxLength={128}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>

        <button type="submit" className="primary" disabled={busy}>
          {busy ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
