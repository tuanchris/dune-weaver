import { useEffect, useRef } from 'react'

/**
 * Hook that triggers a callback when the backend connection is established.
 * Useful for refetching data after the app reconnects to the backend.
 */
export function useOnBackendConnected(callback: () => void) {
  const callbackRef = useRef(callback)

  // Keep callback ref up to date
  useEffect(() => {
    callbackRef.current = callback
  }, [callback])

  useEffect(() => {
    const handleConnected = () => {
      callbackRef.current()
    }

    window.addEventListener('backend-connected', handleConnected)
    return () => {
      window.removeEventListener('backend-connected', handleConnected)
    }
  }, [])
}

/**
 * Hook that returns a function wrapped to also be called on backend reconnection.
 * Automatically calls the function on mount and whenever backend reconnects.
 */
export function useFetchOnConnect<T extends (...args: unknown[]) => unknown>(fetchFn: T): T {
  const fetchRef = useRef(fetchFn)

  useEffect(() => {
    fetchRef.current = fetchFn
  }, [fetchFn])

  // Call on backend connect
  useOnBackendConnected(() => {
    fetchRef.current()
  })

  return fetchFn
}
