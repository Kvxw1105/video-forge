import React, { Component, ErrorInfo, ReactNode } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '100vh',
    padding: '2rem',
    backgroundColor: 'var(--bg-surface, #1a1a2e)',
    color: 'var(--text-primary, #e0e0e0)',
    fontFamily: 'inherit',
  },
  icon: {
    fontSize: '4rem',
    marginBottom: '1.5rem',
    color: 'var(--danger, #ff4444)',
  },
  title: {
    fontSize: '1.5rem',
    fontWeight: 600,
    marginBottom: '0.75rem',
    color: 'var(--text-primary, #e0e0e0)',
  },
  message: {
    fontSize: '0.875rem',
    color: 'var(--text-muted, #888)',
    marginBottom: '2rem',
    maxWidth: '480px',
    textAlign: 'center',
    lineHeight: 1.6,
    wordBreak: 'break-word',
  },
  button: {
    padding: '0.625rem 1.5rem',
    fontSize: '0.875rem',
    fontWeight: 500,
    color: '#fff',
    backgroundColor: 'var(--accent, #6c63ff)',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    transition: 'opacity 0.2s ease',
  },
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div style={styles.container}>
          <div style={styles.icon}>&#x26A0;</div>
          <h1 style={styles.title}>Something went wrong</h1>
          <p style={styles.message}>
            {this.state.error?.message || 'An unexpected error occurred.'}
          </p>
          <button
            style={styles.button}
            onClick={() => window.location.reload()}
            onMouseEnter={(e) => { (e.target as HTMLButtonElement).style.opacity = '0.85' }}
            onMouseLeave={(e) => { (e.target as HTMLButtonElement).style.opacity = '1' }}
          >
            Reload
          </button>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
