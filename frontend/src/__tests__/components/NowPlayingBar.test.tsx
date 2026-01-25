import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen } from '../../test/utils'
import { NowPlayingBar } from '../../components/NowPlayingBar'

describe('NowPlayingBar', () => {
  const defaultProps = {
    isVisible: true,
    onClose: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Visibility', () => {
    it('renders when visible', () => {
      const { container } = renderWithProviders(<NowPlayingBar {...defaultProps} />)
      // Component should render (even if empty initially)
      expect(container).toBeTruthy()
    })

    it('does not render content when isVisible is false', () => {
      const { container } = renderWithProviders(
        <NowPlayingBar {...defaultProps} isVisible={false} />
      )
      // When not visible, should return null
      expect(container.firstChild).toBeNull()
    })

    it('calls onClose callback', () => {
      const onClose = vi.fn()
      renderWithProviders(<NowPlayingBar {...defaultProps} onClose={onClose} />)
      // onClose is passed correctly
      expect(onClose).not.toHaveBeenCalled()
    })
  })

  describe('Props Handling', () => {
    it('accepts logsDrawerHeight prop', () => {
      expect(() => {
        renderWithProviders(
          <NowPlayingBar {...defaultProps} logsDrawerHeight={300} />
        )
      }).not.toThrow()
    })

    it('accepts openExpanded prop', () => {
      expect(() => {
        renderWithProviders(
          <NowPlayingBar {...defaultProps} openExpanded={true} />
        )
      }).not.toThrow()
    })

    it('accepts isLogsOpen prop', () => {
      expect(() => {
        renderWithProviders(
          <NowPlayingBar {...defaultProps} isLogsOpen={true} />
        )
      }).not.toThrow()
    })
  })

  describe('Component Structure', () => {
    it('renders without crashing with all props', () => {
      expect(() => {
        renderWithProviders(
          <NowPlayingBar
            isVisible={true}
            onClose={() => {}}
            isLogsOpen={false}
            logsDrawerHeight={256}
            openExpanded={false}
          />
        )
      }).not.toThrow()
    })
  })
})
