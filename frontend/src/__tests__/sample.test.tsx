import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'

// Simple component for testing infrastructure
function SampleComponent({ message }: { message: string }) {
  return <div data-testid="sample">{message}</div>
}

describe('Test Infrastructure', () => {
  it('renders component with React Testing Library', () => {
    render(<SampleComponent message="Hello Test" />)
    expect(screen.getByTestId('sample')).toHaveTextContent('Hello Test')
  })

  it('has jest-dom matchers available', () => {
    render(<SampleComponent message="Visible" />)
    expect(screen.getByTestId('sample')).toBeInTheDocument()
    expect(screen.getByTestId('sample')).toBeVisible()
  })
})
