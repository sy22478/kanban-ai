import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api, readable } from '../api'
import { useAuth } from '../auth'

/** Agrees with RegisterRequest's min_length. The server is still the authority;
 *  this only means the obvious case is answered without a round trip. */
const MINIMUM_PASSWORD = 12

export function RegisterPage() {
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
      // Registration signs you in: the server sets the session cookie on the
      // 201, so there is no second login step and no window where the account
      // exists but the person is still on this page.
      signedIn(await api.register(email, password))
    } catch (cause) {
      // A duplicate address is a 409 whose detail says so in words. Showing the
      // detail rather than the whole "POST /auth/register failed with 409"
      // string is the difference between an instruction and a stack trace.
      setError(readable(cause))
      setBusy(false)
      return
    }

    navigate('/', { replace: true })
  }

  return (
    <main className="page auth-page">
      <h1>Create an account</h1>

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
            autoComplete="new-password"
            required
            minLength={MINIMUM_PASSWORD}
            maxLength={128}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>

        <p className="muted">At least {MINIMUM_PASSWORD} characters.</p>

        <button type="submit" className="primary" disabled={busy}>
          {busy ? 'Creating...' : 'Create account'}
        </button>
      </form>

      <p className="muted">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </main>
  )
}
