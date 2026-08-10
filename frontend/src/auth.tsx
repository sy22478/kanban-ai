import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { Navigate, Outlet } from 'react-router-dom'

import { ApiError, api, setUnauthorizedHandler } from './api'
import type { User } from './types'

/** `undefined` means the GET /api/me that answers the question has not come back
 *  yet. It is a third state on purpose: collapsing it into "signed out" is what
 *  makes an app show its login page for a moment on every reload. */
type Known = User | null | undefined

type Auth = {
  user: Known
  signedIn: (user: User) => void
  signedOut: () => void
}

const AuthContext = createContext<Auth | null>(null)

export function useAuth(): Auth {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth used outside AuthProvider')
  return value
}

/** Holds the answer to "who is signed in", for the whole app.
 *
 *  There is exactly one place that can answer it: GET /api/me. The session
 *  cookie is HttpOnly, so JavaScript cannot see it, and the presence of a cookie
 *  would not prove it was still valid anyway. The server decides.
 *
 *  It is a layout route rather than a wrapper around RouterProvider, because the
 *  sign-out control inside it needs useNavigate, which only exists inside the
 *  router.
 */
export function AuthProvider() {
  const [user, setUser] = useState<Known>(undefined)

  const signedIn = useCallback((next: User) => setUser(next), [])
  const signedOut = useCallback(() => setUser(null), [])

  useEffect(() => {
    // One redirect rule for the whole app, rather than a 401 check repeated at
    // every call site. Any request that comes back 401 clears the user, and
    // RequireAuth below turns that into a redirect on the next render.
    setUnauthorizedHandler(() => setUser(null))
    return () => setUnauthorizedHandler(null)
  }, [])

  useEffect(() => {
    // StrictMode runs this twice in development; `live` stops the discarded
    // first run from writing state after it has been cleaned up.
    let live = true

    api
      .me()
      .then((found) => live && setUser(found))
      .catch((cause) => {
        // A 401 is the expected answer for a visitor with no session. Anything
        // else -- a stopped back-end, a proxy error -- is also treated as signed
        // out, which sends them to /login where the next request will fail with
        // the real reason on screen. Guessing "probably signed in" here would
        // render a board page that cannot load anything.
        if (!live) return
        if (!(cause instanceof ApiError) || cause.status !== 401) {
          console.warn('Could not determine sign-in state:', cause)
        }
        setUser(null)
      })

    return () => {
      live = false
    }
  }, [])

  return (
    <AuthContext.Provider value={{ user, signedIn, signedOut }}>
      <Outlet />
    </AuthContext.Provider>
  )
}

/** Everything behind it requires a signed-in user.
 *
 *  While the check is in flight it renders a placeholder rather than the login
 *  page. That is the deliberate cost: a signed-in user reloading sees "Checking
 *  your session" for as long as /api/me takes instead of a flash of a login form
 *  they do not need, and a signed-out user waits that same moment before being
 *  sent on. The alternative -- assume signed out, redirect immediately, bounce
 *  back when /api/me answers -- is faster for nobody and jumps twice.
 */
export function RequireAuth() {
  const { user } = useAuth()

  if (user === undefined) {
    return (
      <main className="page">
        <p>Checking your session...</p>
      </main>
    )
  }

  if (user === null) return <Navigate to="/login" replace />

  return <Outlet />
}

/** Only for /login and /register: a signed-in visitor has no business there. */
export function RedirectIfSignedIn({ children }: { children: ReactNode }) {
  const { user } = useAuth()

  if (user === undefined) {
    return (
      <main className="page">
        <p>Checking your session...</p>
      </main>
    )
  }

  if (user) return <Navigate to="/" replace />

  return <>{children}</>
}
