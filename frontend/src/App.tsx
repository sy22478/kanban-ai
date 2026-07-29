import { useEffect, useState } from 'react'

type User = {
  id: string
  email: string
}

export default function App() {
  const [users, setUsers] = useState<User[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/users')
      .then((response) => {
        if (!response.ok) {
          throw new Error(`the API returned ${response.status}`)
        }
        return response.json()
      })
      .then(setUsers)
      .catch((cause: Error) => setError(cause.message))
  }, [])

  return (
    <main style={{ fontFamily: 'system-ui, sans-serif', padding: '2rem' }}>
      <h1>Kanban AI</h1>
      <p>Users read from Postgres through the API:</p>
      {/* No fallback value. If the database or the API is down this shows the
          failure rather than something that looks like success. */}
      {error !== null ? (
        <p>Could not reach the API: {error}</p>
      ) : users === null ? (
        <p>Loading...</p>
      ) : (
        <ul>
          {users.map((user) => (
            <li key={user.id}>
              {user.email} <small>({user.id})</small>
            </li>
          ))}
        </ul>
      )}
    </main>
  )
}
