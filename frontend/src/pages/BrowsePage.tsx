import { useState, useEffect, useMemo, useRef, useCallback, createContext, useContext } from 'react'
import { toast } from 'sonner'
import {
  initPreviewCacheDB,
  getPreviewsFromCache,
  savePreviewToCache,
  cacheAllPreviews,
} from '@/lib/previewCache'
import { fuzzyMatch } from '@/lib/utils'
import { useOnBackendConnected } from '@/hooks/useBackendConnection'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Slider } from '@/components/ui/slider'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

// Types
interface PatternMetadata {
  path: string
  name: string
  category: string
  date_modified: number
  coordinates_count: number
}

interface PreviewData {
  image_data: string
  first_coordinate: { x: number; y: number } | null
  last_coordinate: { x: number; y: number } | null
  error?: string
}

// Coordinates come as [theta, rho] tuples from the backend
type Coordinate = [number, number]

type SortOption = 'name' | 'date' | 'category'
type PreExecution = 'none' | 'adaptive' | 'clear_from_in' | 'clear_from_out' | 'clear_sideway'

const preExecutionOptions: { value: PreExecution; label: string }[] = [
  { value: 'adaptive', label: 'Adaptive' },
  { value: 'clear_from_in', label: 'Clear From Center' },
  { value: 'clear_from_out', label: 'Clear From Perimeter' },
  { value: 'clear_sideway', label: 'Clear Sideway' },
  { value: 'none', label: 'None' },
]

// Context for lazy loading previews
interface PreviewContextType {
  requestPreview: (path: string) => void
  previews: Record<string, PreviewData>
}

const PreviewContext = createContext<PreviewContextType | null>(null)

export function BrowsePage() {
  // Data state
  const [patterns, setPatterns] = useState<PatternMetadata[]>([])
  const [previews, setPreviews] = useState<Record<string, PreviewData>>({})
  const [isLoading, setIsLoading] = useState(true)

  // Filter/sort state
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  const [sortBy, setSortBy] = useState<SortOption>('name')
  const [sortAsc, setSortAsc] = useState(true)

  // Selection and panel state
  const [selectedPattern, setSelectedPattern] = useState<PatternMetadata | null>(null)
  const [isPanelOpen, setIsPanelOpen] = useState(false)
  const [preExecution, setPreExecution] = useState<PreExecution>('adaptive')
  const [isRunning, setIsRunning] = useState(false)

  // Animated preview modal state
  const [isAnimatedPreviewOpen, setIsAnimatedPreviewOpen] = useState(false)
  const [coordinates, setCoordinates] = useState<Coordinate[]>([])
  const [isLoadingCoordinates, setIsLoadingCoordinates] = useState(false)
  const [isPlaying, setIsPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [progress, setProgress] = useState(0)

  // Canvas and animation refs
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animationRef = useRef<number | null>(null)
  const currentIndexRef = useRef(0)

  // Lazy loading queue for previews
  const pendingPreviewsRef = useRef<Set<string>>(new Set())
  const batchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Cache all previews state
  const [isCaching, setIsCaching] = useState(false)
  const [cacheProgress, setCacheProgress] = useState(0)
  const [allCached, setAllCached] = useState(false)

  // Favorites state
  const [favorites, setFavorites] = useState<Set<string>>(new Set())

  // Upload state
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isUploading, setIsUploading] = useState(false)

  // Close panel when playback starts
  useEffect(() => {
    const handlePlaybackStarted = () => {
      setIsPanelOpen(false)
    }
    window.addEventListener('playback-started', handlePlaybackStarted)
    return () => window.removeEventListener('playback-started', handlePlaybackStarted)
  }, [])

  // Initialize IndexedDB cache and fetch patterns on mount
  useEffect(() => {
    initPreviewCacheDB().then(() => {
      fetchPatterns()
    }).catch(() => {
      // Continue even if IndexedDB fails - just won't have persistent cache
      fetchPatterns()
    })
    loadFavorites()
  }, [])

  // Refetch when backend reconnects
  useOnBackendConnected(() => {
    fetchPatterns()
    loadFavorites()
  })

  // Load favorites from "Favorites" playlist
  const loadFavorites = async () => {
    try {
      const response = await fetch('/get_playlist?name=Favorites')
      if (response.ok) {
        const playlist = await response.json()
        setFavorites(new Set(playlist.files || []))
      }
    } catch {
      // Favorites playlist doesn't exist yet - that's OK
    }
  }

  // Toggle favorite status for a pattern
  const toggleFavorite = async (path: string, e: React.MouseEvent) => {
    e.stopPropagation() // Don't trigger card click

    const isFavorite = favorites.has(path)
    const newFavorites = new Set(favorites)

    try {
      if (isFavorite) {
        // Remove from favorites
        newFavorites.delete(path)
        const response = await fetch('/modify_playlist', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ playlist_name: 'Favorites', files: Array.from(newFavorites) }),
        })
        if (response.ok) {
          setFavorites(newFavorites)
          toast.success('Removed from favorites')
        }
      } else {
        // Add to favorites - first check if playlist exists
        newFavorites.add(path)
        const checkResponse = await fetch('/get_playlist?name=Favorites')
        if (checkResponse.ok) {
          // Playlist exists, add to it
          await fetch('/add_to_playlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ playlist_name: 'Favorites', pattern: path }),
          })
        } else {
          // Create playlist with this pattern
          await fetch('/create_playlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ playlist_name: 'Favorites', files: [path] }),
          })
        }
        setFavorites(newFavorites)
        toast.success('Added to favorites')
      }
    } catch {
      toast.error('Failed to update favorites')
    }
  }

  const fetchPatterns = async () => {
    setIsLoading(true)
    try {
      const response = await fetch('/list_theta_rho_files_with_metadata')
      const data = await response.json()
      setPatterns(data)

      if (data.length > 0) {
        // Sort patterns by name (default sort) before preloading
        const sortedPatterns = [...data].sort((a: PatternMetadata, b: PatternMetadata) =>
          a.name.localeCompare(b.name)
        )
        const allPaths = data.map((p: PatternMetadata) => p.path)

        // Preload first 30 patterns in sorted order (fills most viewports)
        const initialBatch = sortedPatterns.slice(0, 30).map((p: PatternMetadata) => p.path)
        const cachedPreviews = await getPreviewsFromCache(initialBatch)

        // Immediately display cached previews
        if (cachedPreviews.size > 0) {
          const cachedData: Record<string, PreviewData> = {}
          cachedPreviews.forEach((previewData, path) => {
            cachedData[path] = previewData
          })
          setPreviews(cachedData)
        }

        // Fetch any uncached patterns in the initial batch
        const uncachedInitial = initialBatch.filter((p: string) => !cachedPreviews.has(p))
        if (uncachedInitial.length > 0) {
          fetchPreviewsBatch(uncachedInitial)
        }

        // Check if ALL patterns are cached (for Cache All button)
        const allCachedPreviews = await getPreviewsFromCache(allPaths)
        setAllCached(allCachedPreviews.size === allPaths.length)
      }
    } catch (error) {
      console.error('Error fetching patterns:', error)
      toast.error('Failed to load patterns')
    } finally {
      setIsLoading(false)
    }
  }

  const fetchPreviewsBatch = async (filePaths: string[]) => {
    const BATCH_SIZE = 10 // Process 10 patterns at a time to avoid overwhelming the backend

    try {
      // First check IndexedDB cache for all patterns
      const cachedPreviews = await getPreviewsFromCache(filePaths)

      // Update state with cached previews immediately
      if (cachedPreviews.size > 0) {
        const cachedData: Record<string, PreviewData> = {}
        cachedPreviews.forEach((data, path) => {
          cachedData[path] = data
        })
        setPreviews((prev) => ({ ...prev, ...cachedData }))
      }

      // Find patterns not in cache
      const uncachedPaths = filePaths.filter((path) => !cachedPreviews.has(path))

      // Fetch uncached patterns in batches to avoid overwhelming the backend
      if (uncachedPaths.length > 0) {
        for (let i = 0; i < uncachedPaths.length; i += BATCH_SIZE) {
          const batch = uncachedPaths.slice(i, i + BATCH_SIZE)

          try {
            const response = await fetch('/preview_thr_batch', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ file_names: batch }),
            })
            const data = await response.json()

            // Save fetched previews to IndexedDB cache
            for (const [path, previewData] of Object.entries(data)) {
              if (previewData && !(previewData as PreviewData).error) {
                savePreviewToCache(path, previewData as PreviewData)
              }
            }

            setPreviews((prev) => ({ ...prev, ...data }))
          } catch {
            // Continue with next batch even if one fails
          }

          // Small delay between batches to reduce backend load
          if (i + BATCH_SIZE < uncachedPaths.length) {
            await new Promise((resolve) => setTimeout(resolve, 100))
          }
        }
      }
    } catch (error) {
      console.error('Error fetching previews:', error)
    }
  }

  const fetchCoordinates = async (filePath: string) => {
    setIsLoadingCoordinates(true)
    try {
      const response = await fetch('/get_theta_rho_coordinates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_name: filePath }),
      })
      const data = await response.json()
      setCoordinates(data.coordinates || [])
    } catch (error) {
      console.error('Error fetching coordinates:', error)
      toast.error('Failed to load pattern coordinates')
    } finally {
      setIsLoadingCoordinates(false)
    }
  }

  // Get unique categories
  const categories = useMemo(() => {
    const cats = new Set(patterns.map((p) => p.category))
    return ['all', ...Array.from(cats).sort()]
  }, [patterns])

  // Filter and sort patterns
  const filteredPatterns = useMemo(() => {
    let result = patterns

    if (selectedCategory !== 'all') {
      result = result.filter((p) => p.category === selectedCategory)
    }

    if (searchQuery) {
      result = result.filter(
        (p) =>
          fuzzyMatch(p.name, searchQuery) ||
          fuzzyMatch(p.category, searchQuery)
      )
    }

    result = [...result].sort((a, b) => {
      let comparison = 0
      switch (sortBy) {
        case 'name':
          comparison = a.name.localeCompare(b.name)
          break
        case 'date':
          comparison = a.date_modified - b.date_modified
          break
        case 'category':
          comparison = a.category.localeCompare(b.category) || a.name.localeCompare(b.name)
          break
        default:
          return 0
      }
      return sortAsc ? comparison : -comparison
    })

    return result
  }, [patterns, selectedCategory, searchQuery, sortBy, sortAsc])

  // Batched preview loading - collects requests and fetches in batches
  const requestPreview = useCallback((path: string) => {
    // Skip if already loaded or pending
    if (previews[path] || pendingPreviewsRef.current.has(path)) return

    pendingPreviewsRef.current.add(path)

    // Clear existing timeout and set a new one to batch requests
    if (batchTimeoutRef.current) {
      clearTimeout(batchTimeoutRef.current)
    }

    batchTimeoutRef.current = setTimeout(() => {
      const pathsToFetch = Array.from(pendingPreviewsRef.current)
      if (pathsToFetch.length > 0) {
        pendingPreviewsRef.current.clear()
        fetchPreviewsBatch(pathsToFetch)
      }
    }, 50) // Batch requests within 50ms window
  }, [previews])

  // Canvas drawing functions
  const polarToCartesian = useCallback((theta: number, rho: number, size: number) => {
    const centerX = size / 2
    const centerY = size / 2
    const radius = (size / 2) * 0.9 * rho
    const x = centerX + radius * Math.cos(theta)
    const y = centerY + radius * Math.sin(theta)
    return { x, y }
  }, [])

  // Offscreen canvas for the pattern path (performance optimization)
  const offscreenCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const lastDrawnIndexRef = useRef<number>(-1)
  const lastThemeRef = useRef<boolean | null>(null)

  // Get theme colors
  const getThemeColors = useCallback(() => {
    const isDark = document.documentElement.classList.contains('dark')
    return {
      isDark,
      bgOuter: isDark ? '#1a1a1a' : '#f5f5f5',
      bgInner: isDark ? '#262626' : '#ffffff',
      borderColor: isDark ? 'rgba(255, 255, 255, 0.2)' : 'rgba(128, 128, 128, 0.3)',
      lineColor: isDark ? '#e5e5e5' : '#333333',
      markerBorder: isDark ? '#333333' : '#ffffff',
    }
  }, [])

  // Initialize or reset offscreen canvas
  const initOffscreenCanvas = useCallback((size: number, coords: Coordinate[]) => {
    const colors = getThemeColors()

    // Create offscreen canvas if needed
    if (!offscreenCanvasRef.current) {
      offscreenCanvasRef.current = document.createElement('canvas')
    }

    const offscreen = offscreenCanvasRef.current
    offscreen.width = size
    offscreen.height = size

    const ctx = offscreen.getContext('2d')
    if (!ctx) return

    // Draw background
    ctx.fillStyle = colors.bgOuter
    ctx.fillRect(0, 0, size, size)

    // Draw background circle
    ctx.beginPath()
    ctx.arc(size / 2, size / 2, (size / 2) * 0.95, 0, Math.PI * 2)
    ctx.fillStyle = colors.bgInner
    ctx.fill()
    ctx.strokeStyle = colors.borderColor
    ctx.lineWidth = 1
    ctx.stroke()

    // Setup line style for incremental drawing
    ctx.strokeStyle = colors.lineColor
    ctx.lineWidth = 1
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'

    // Draw initial point if we have coordinates
    if (coords.length > 0) {
      const firstPoint = polarToCartesian(coords[0][0], coords[0][1], size)
      ctx.beginPath()
      ctx.moveTo(firstPoint.x, firstPoint.y)
      ctx.stroke()
    }

    lastDrawnIndexRef.current = 0
    lastThemeRef.current = colors.isDark
  }, [getThemeColors, polarToCartesian])

  // Draw pattern incrementally for performance
  const drawPattern = useCallback((ctx: CanvasRenderingContext2D, coords: Coordinate[], upToIndex: number, forceRedraw = false) => {
    const canvas = ctx.canvas
    const size = canvas.width
    const colors = getThemeColors()

    // Check if we need to reinitialize (theme change or reset)
    const needsReinit = forceRedraw ||
      !offscreenCanvasRef.current ||
      lastThemeRef.current !== colors.isDark ||
      upToIndex < lastDrawnIndexRef.current

    if (needsReinit) {
      initOffscreenCanvas(size, coords)
    }

    const offscreen = offscreenCanvasRef.current
    if (!offscreen) return

    const offCtx = offscreen.getContext('2d')
    if (!offCtx) return

    // Draw new segments incrementally on offscreen canvas
    if (coords.length > 0 && upToIndex > lastDrawnIndexRef.current) {
      offCtx.strokeStyle = colors.lineColor
      offCtx.lineWidth = 1
      offCtx.lineCap = 'round'
      offCtx.lineJoin = 'round'

      offCtx.beginPath()
      const startPoint = polarToCartesian(
        coords[lastDrawnIndexRef.current][0],
        coords[lastDrawnIndexRef.current][1],
        size
      )
      offCtx.moveTo(startPoint.x, startPoint.y)

      for (let i = lastDrawnIndexRef.current + 1; i <= upToIndex && i < coords.length; i++) {
        const point = polarToCartesian(coords[i][0], coords[i][1], size)
        offCtx.lineTo(point.x, point.y)
      }
      offCtx.stroke()

      lastDrawnIndexRef.current = upToIndex
    }

    // Copy offscreen canvas to main canvas
    ctx.drawImage(offscreen, 0, 0)

    // Draw current position marker on main canvas
    if (upToIndex < coords.length && coords.length > 0) {
      const currentPoint = polarToCartesian(coords[upToIndex][0], coords[upToIndex][1], size)
      ctx.beginPath()
      ctx.arc(currentPoint.x, currentPoint.y, 5, 0, Math.PI * 2)
      ctx.fillStyle = '#0b80ee'
      ctx.fill()
      ctx.strokeStyle = colors.markerBorder
      ctx.lineWidth = 1
      ctx.stroke()
    }
  }, [getThemeColors, initOffscreenCanvas, polarToCartesian])

  // Animation loop
  useEffect(() => {
    if (!isPlaying || coordinates.length === 0 || !canvasRef.current) return

    const ctx = canvasRef.current.getContext('2d')
    if (!ctx) return

    let lastTime = performance.now()
    const coordsPerSecond = 100 * speed

    const animate = (currentTime: number) => {
      const deltaTime = (currentTime - lastTime) / 1000
      lastTime = currentTime

      const coordsToAdvance = Math.floor(deltaTime * coordsPerSecond)
      currentIndexRef.current = Math.min(
        currentIndexRef.current + Math.max(1, coordsToAdvance),
        coordinates.length - 1
      )

      drawPattern(ctx, coordinates, currentIndexRef.current)
      setProgress((currentIndexRef.current / (coordinates.length - 1)) * 100)

      if (currentIndexRef.current < coordinates.length - 1) {
        animationRef.current = requestAnimationFrame(animate)
      } else {
        setIsPlaying(false)
      }
    }

    animationRef.current = requestAnimationFrame(animate)

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [isPlaying, coordinates, speed, drawPattern])

  // Draw initial state when coordinates load
  useEffect(() => {
    if (coordinates.length > 0 && canvasRef.current) {
      const ctx = canvasRef.current.getContext('2d')
      if (ctx) {
        currentIndexRef.current = 0
        setProgress(0)
        drawPattern(ctx, coordinates, 0, true) // Force redraw on new pattern
      }
    }
  }, [coordinates, drawPattern])

  const handlePatternClick = (pattern: PatternMetadata) => {
    setSelectedPattern(pattern)
    setIsPanelOpen(true)
    setPreExecution('adaptive')
  }

  const handleClosePanel = () => {
    setIsPanelOpen(false)
  }

  // Swipe to close panel handling
  const panelRef = useRef<HTMLDivElement>(null)
  const panelTouchStartX = useRef<number | null>(null)

  const handlePanelTouchStart = (e: React.TouchEvent) => {
    panelTouchStartX.current = e.touches[0].clientX
  }
  const handlePanelTouchEnd = (e: React.TouchEvent) => {
    if (panelTouchStartX.current === null) return
    const touchEndX = e.changedTouches[0].clientX
    const deltaX = touchEndX - panelTouchStartX.current
    // Swipe right more than 50px to close
    if (deltaX > 50) {
      handleClosePanel()
    }
    panelTouchStartX.current = null
  }

  const handleOpenAnimatedPreview = async () => {
    if (!selectedPattern) return
    setIsAnimatedPreviewOpen(true)
    setIsPlaying(false)
    setProgress(0)
    currentIndexRef.current = 0
    await fetchCoordinates(selectedPattern.path)
    // Auto-play after coordinates load
    setIsPlaying(true)
  }

  const handleCloseAnimatedPreview = () => {
    setIsAnimatedPreviewOpen(false)
    setIsPlaying(false)
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current)
    }
    setCoordinates([])
  }

  const handlePlayPause = () => {
    if (isPlaying) {
      setIsPlaying(false)
    } else {
      if (currentIndexRef.current >= coordinates.length - 1) {
        currentIndexRef.current = 0
        setProgress(0)
      }
      setIsPlaying(true)
    }
  }

  const handleReset = () => {
    setIsPlaying(false)
    currentIndexRef.current = 0
    setProgress(0)
    if (canvasRef.current && coordinates.length > 0) {
      const ctx = canvasRef.current.getContext('2d')
      if (ctx) {
        drawPattern(ctx, coordinates, 0, true) // Force redraw on reset
      }
    }
  }

  const handleProgressChange = (value: number[]) => {
    const newProgress = value[0]
    setProgress(newProgress)
    currentIndexRef.current = Math.floor((newProgress / 100) * (coordinates.length - 1))

    if (canvasRef.current && coordinates.length > 0) {
      const ctx = canvasRef.current.getContext('2d')
      if (ctx) {
        drawPattern(ctx, coordinates, currentIndexRef.current)
      }
    }
  }

  const handleRunPattern = async () => {
    if (!selectedPattern) return

    setIsRunning(true)
    try {
      const response = await fetch('/run_theta_rho', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_name: selectedPattern.path,
          pre_execution: preExecution,
        }),
      })

      if (response.status === 409) {
        toast.error('Another pattern is already running')
      } else if (response.ok) {
        toast.success(`Running ${selectedPattern.name}`)
      } else {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to run pattern')
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to run pattern')
    } finally {
      setIsRunning(false)
    }
  }

  const handleDeletePattern = async () => {
    if (!selectedPattern) return

    if (!selectedPattern.path.startsWith('custom_patterns/')) {
      toast.error('Only custom patterns can be deleted')
      return
    }

    if (!confirm(`Delete "${selectedPattern.name}"? This cannot be undone.`)) {
      return
    }

    try {
      const response = await fetch('/delete_theta_rho_file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_name: selectedPattern.path }),
      })

      if (response.ok) {
        toast.success(`Deleted ${selectedPattern.name}`)
        setIsPanelOpen(false)
        setSelectedPattern(null)
        fetchPatterns()
      } else {
        throw new Error('Failed to delete pattern')
      }
    } catch (error) {
      toast.error('Failed to delete pattern')
    }
  }

  const getPreviewUrl = (path: string) => {
    const preview = previews[path]
    return preview?.image_data || null
  }

  const formatCoordinate = (coord: { x: number; y: number } | null) => {
    if (!coord) return '(-, -)'
    return `(${coord.x.toFixed(2)}, ${coord.y.toFixed(2)})`
  }

  const canDelete = selectedPattern?.path.startsWith('custom_patterns/')

  // Cache all previews handler
  const handleCacheAllPreviews = async () => {
    if (isCaching) return

    setIsCaching(true)
    setCacheProgress(0)

    const result = await cacheAllPreviews((progress) => {
      const percentage = progress.total > 0
        ? Math.round((progress.completed / progress.total) * 100)
        : 0
      setCacheProgress(percentage)
    })

    if (result.success) {
      setAllCached(true)
      if (result.cached === 0) {
        toast.success('All patterns are already cached!')
      } else {
        toast.success('All pattern previews have been cached!')
      }
    } else {
      toast.error('Failed to cache previews')
    }

    setIsCaching(false)
    setCacheProgress(0)
  }

  // Handle pattern file upload
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Validate file extension
    if (!file.name.endsWith('.thr')) {
      toast.error('Please select a .thr file')
      return
    }

    setIsUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch('/upload_theta_rho', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Upload failed')
      }

      toast.success(`Pattern "${file.name}" uploaded successfully`)

      // Refresh patterns list
      const patternsRes = await fetch('/list_theta_rho_files')
      if (patternsRes.ok) {
        const data = await patternsRes.json()
        setPatterns(data.files || [])
      }
    } catch (error) {
      console.error('Upload error:', error)
      toast.error(error instanceof Error ? error.message : 'Failed to upload pattern')
    } finally {
      setIsUploading(false)
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <span className="material-icons-outlined animate-spin text-4xl text-muted-foreground">
          sync
        </span>
      </div>
    )
  }

  return (
    <div className={`flex flex-col w-full max-w-5xl mx-auto gap-6 py-6 px-4 transition-all duration-300 ${isPanelOpen ? 'lg:mr-[28rem]' : ''}`}>
      {/* Hidden file input for pattern upload */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".thr"
        onChange={handleFileUpload}
        className="hidden"
      />

      {/* Page Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-3xl font-bold tracking-tight">Browse Patterns</h1>
          <p className="text-muted-foreground">
            Explore and run patterns on your sand table · {patterns.length} patterns available
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          className="gap-2 shrink-0"
        >
          {isUploading ? (
            <span className="material-icons-outlined animate-spin text-lg">sync</span>
          ) : (
            <span className="material-icons-outlined text-lg">add</span>
          )}
          <span className="hidden sm:inline">Add Pattern</span>
        </Button>
      </div>

      <Separator />

      {/* Sticky Filters */}
      <div className="sticky top-14 z-30 py-4 -mx-4 px-4 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1">
            <div className="relative">
              <span className="material-icons-outlined absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-xl">
                search
              </span>
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search patterns..."
                className="pl-10 pr-10"
              />
              {searchQuery && (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setSearchQuery('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  <span className="material-icons-outlined text-xl">close</span>
                </Button>
              )}
            </div>
          </div>

          <Select value={selectedCategory} onValueChange={setSelectedCategory}>
            <SelectTrigger className="w-full sm:w-44">
              <SelectValue placeholder="Category" />
            </SelectTrigger>
            <SelectContent>
              {categories.map((cat) => (
                <SelectItem key={cat} value={cat}>
                  {cat === 'all' ? 'All Categories' : cat === 'root' ? 'Uncategorized' : cat}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <div className="flex gap-2">
            <Select value={sortBy} onValueChange={(v) => setSortBy(v as SortOption)}>
              <SelectTrigger className="w-full sm:w-36">
                <SelectValue placeholder="Sort by" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="name">Name</SelectItem>
                <SelectItem value="date">Date Modified</SelectItem>
                <SelectItem value="category">Category</SelectItem>
              </SelectContent>
            </Select>

            <Button
              variant="outline"
              size="icon"
              onClick={() => setSortAsc(!sortAsc)}
              className="shrink-0"
              title={sortAsc ? 'Ascending' : 'Descending'}
            >
              <span className="material-icons-outlined text-lg">
                {sortAsc ? 'arrow_upward' : 'arrow_downward'}
              </span>
            </Button>
          </div>

          {!allCached && (
            <Button
              variant="outline"
              onClick={handleCacheAllPreviews}
              className="gap-2 whitespace-nowrap"
            >
              {isCaching ? (
                <>
                  <span className="material-icons-outlined animate-spin text-lg">sync</span>
                  <span>{cacheProgress}%</span>
                </>
              ) : (
                <>
                  <span className="material-icons-outlined text-lg">cached</span>
                  <span className="hidden sm:inline">Cache All</span>
                </>
              )}
            </Button>
          )}
        </div>
      </div>

      {(searchQuery || selectedCategory !== 'all') && (
        <p className="text-sm text-muted-foreground">
          Showing {filteredPatterns.length} of {patterns.length} patterns
        </p>
      )}

      {/* Pattern Grid */}
      {filteredPatterns.length === 0 ? (
        <div className="flex flex-col items-center justify-center min-h-[40vh] gap-4 text-center">
          <div className="p-4 rounded-full bg-muted">
            <span className="material-icons-outlined text-5xl text-muted-foreground">
              search_off
            </span>
          </div>
          <div className="space-y-1">
            <h2 className="text-xl font-semibold">No patterns found</h2>
            <p className="text-muted-foreground">Try adjusting your search or filters</p>
          </div>
          {(searchQuery || selectedCategory !== 'all') && (
            <Button
              variant="outline"
              onClick={() => {
                setSearchQuery('')
                setSelectedCategory('all')
              }}
            >
              Clear Filters
            </Button>
          )}
        </div>
      ) : (
        <PreviewContext.Provider value={{ requestPreview, previews }}>
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-2 sm:gap-4">
            {filteredPatterns.map((pattern) => (
              <PatternCard
                key={pattern.path}
                pattern={pattern}
                isSelected={selectedPattern?.path === pattern.path}
                isFavorite={favorites.has(pattern.path)}
                onToggleFavorite={toggleFavorite}
                onClick={() => handlePatternClick(pattern)}
              />
            ))}
          </div>
        </PreviewContext.Provider>
      )}

      <div className="h-48" />

      {/* Slide-in Preview Panel */}
      <div
        className={`fixed top-0 bottom-0 right-0 w-full max-w-md transform transition-transform duration-300 ease-in-out z-40 ${
          isPanelOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
        ref={panelRef}
        onTouchStart={handlePanelTouchStart}
        onTouchEnd={handlePanelTouchEnd}
      >
        <div className="h-full bg-background border-l shadow-xl flex flex-col">
          <header className="flex h-14 items-center justify-between border-b px-4 shrink-0">
            <h2 className="text-lg font-semibold truncate pr-4">
              {selectedPattern?.name || 'Pattern Details'}
            </h2>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleClosePanel}
              className="rounded-full text-muted-foreground"
            >
              <span className="material-icons-outlined">close</span>
            </Button>
          </header>

          {selectedPattern && (
            <div className="p-6 overflow-y-auto flex-1">
              {/* Clickable Round Preview Image */}
              <div
                className="mb-6 aspect-square w-full max-w-[280px] mx-auto overflow-hidden rounded-full border bg-muted relative group cursor-pointer"
                onClick={handleOpenAnimatedPreview}
              >
                {getPreviewUrl(selectedPattern.path) ? (
                  <img
                    src={getPreviewUrl(selectedPattern.path)!}
                    alt={selectedPattern.name}
                    className="w-full h-full object-cover pattern-preview"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <span className="material-icons-outlined text-4xl text-muted-foreground">
                      image
                    </span>
                  </div>
                )}
                {/* Play overlay on hover */}
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200 bg-black/20">
                  <div className="bg-background rounded-full w-12 h-12 flex items-center justify-center shadow-lg">
                    <span className="material-icons text-2xl">play_arrow</span>
                  </div>
                </div>
              </div>

              {/* Coordinates */}
              <div className="mb-6 flex justify-between text-sm">
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground">First:</span>
                  <span className="font-semibold">
                    {formatCoordinate(previews[selectedPattern.path]?.first_coordinate)}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground">Last:</span>
                  <span className="font-semibold">
                    {formatCoordinate(previews[selectedPattern.path]?.last_coordinate)}
                  </span>
                </div>
              </div>

              {/* Pre-Execution Options */}
              <div className="mb-6">
                <Label className="text-sm font-semibold mb-3 block">Pre-Execution Action</Label>
                <div className="grid grid-cols-2 gap-2">
                  {preExecutionOptions.map((option) => (
                    <label
                      key={option.value}
                      className={`relative flex cursor-pointer items-center justify-center rounded-lg border p-2.5 text-center text-sm font-medium transition-all hover:border-primary ${
                        preExecution === option.value
                          ? 'border-primary bg-primary text-primary-foreground ring-2 ring-primary ring-offset-2 ring-offset-background'
                          : 'border-border text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      {option.label}
                      <input
                        type="radio"
                        name="preExecutionAction"
                        value={option.value}
                        checked={preExecution === option.value}
                        onChange={() => setPreExecution(option.value)}
                        className="sr-only"
                      />
                    </label>
                  ))}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="space-y-3">
                <Button
                  onClick={handleRunPattern}
                  disabled={isRunning}
                  className="w-full gap-2"
                  size="lg"
                >
                  {isRunning ? (
                    <span className="material-icons-outlined animate-spin text-lg">sync</span>
                  ) : (
                    <span className="material-icons text-lg">play_arrow</span>
                  )}
                  Play
                </Button>

                <Button
                  variant="outline"
                  onClick={handleDeletePattern}
                  disabled={!canDelete}
                  className={`w-full gap-2 ${
                    canDelete
                      ? 'border-destructive text-destructive hover:bg-destructive/10'
                      : 'opacity-50 cursor-not-allowed'
                  }`}
                  size="lg"
                >
                  <span className="material-icons text-lg">delete</span>
                  Delete
                </Button>

                {!canDelete && selectedPattern && (
                  <p className="text-xs text-muted-foreground text-center">
                    Only custom patterns can be deleted
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Backdrop for mobile panel */}
      {isPanelOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={handleClosePanel}
        />
      )}

      {/* Animated Preview Modal */}
      {isAnimatedPreviewOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
          onClick={handleCloseAnimatedPreview}
        >
          <div
            className="bg-background rounded-lg shadow-xl max-w-4xl w-full max-h-[95vh] flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between p-6 border-b shrink-0">
              <h3 className="text-xl font-semibold">
                {selectedPattern?.name || 'Animated Preview'}
              </h3>
              <Button
                variant="ghost"
                size="icon"
                onClick={handleCloseAnimatedPreview}
                className="rounded-full"
              >
                <span className="material-icons text-2xl">close</span>
              </Button>
            </div>

            {/* Modal Content */}
            <div className="p-6 overflow-y-auto flex-1 flex justify-center items-center">
              {isLoadingCoordinates ? (
                <div className="w-[400px] h-[400px] flex items-center justify-center rounded-full bg-muted">
                  <span className="material-icons-outlined animate-spin text-4xl text-muted-foreground">
                    sync
                  </span>
                </div>
              ) : (
                <div className="relative">
                  <canvas
                    ref={canvasRef}
                    width={400}
                    height={400}
                    className="rounded-full"
                  />
                  {/* Play/Pause overlay */}
                  <div
                    className="absolute inset-0 flex items-center justify-center cursor-pointer rounded-full opacity-0 hover:opacity-100 transition-opacity bg-black/10"
                    onClick={handlePlayPause}
                  >
                    <div className="bg-background rounded-full w-16 h-16 flex items-center justify-center shadow-lg">
                      <span className="material-icons text-3xl">
                        {isPlaying ? 'pause' : 'play_arrow'}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Controls */}
            <div className="p-6 space-y-4 shrink-0 border-t">
              {/* Speed Control */}
              <div>
                <div className="flex justify-between mb-2">
                  <Label className="text-sm font-medium">Speed</Label>
                  <span className="text-sm text-muted-foreground">{speed}x</span>
                </div>
                <Slider
                  value={[speed]}
                  onValueChange={(v) => setSpeed(v[0])}
                  min={0.1}
                  max={5}
                  step={0.1}
                  className="py-2"
                />
              </div>

              {/* Progress Control */}
              <div>
                <div className="flex justify-between mb-2">
                  <Label className="text-sm font-medium">Progress</Label>
                  <span className="text-sm text-muted-foreground">{progress.toFixed(0)}%</span>
                </div>
                <Slider
                  value={[progress]}
                  onValueChange={handleProgressChange}
                  min={0}
                  max={100}
                  step={0.1}
                  className="py-2"
                />
              </div>

              {/* Control Buttons */}
              <div className="flex items-center justify-center gap-4">
                <Button onClick={handlePlayPause} className="gap-2">
                  <span className="material-icons">
                    {isPlaying ? 'pause' : 'play_arrow'}
                  </span>
                  {isPlaying ? 'Pause' : 'Play'}
                </Button>
                <Button variant="outline" onClick={handleReset} className="gap-2">
                  <span className="material-icons">replay</span>
                  Reset
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// Pattern Card Component
interface PatternCardProps {
  pattern: PatternMetadata
  isSelected: boolean
  isFavorite: boolean
  onToggleFavorite: (path: string, e: React.MouseEvent) => void
  onClick: () => void
}

function PatternCard({ pattern, isSelected, isFavorite, onToggleFavorite, onClick }: PatternCardProps) {
  const [imageLoaded, setImageLoaded] = useState(false)
  const [imageError, setImageError] = useState(false)
  const cardRef = useRef<HTMLButtonElement>(null)
  const context = useContext(PreviewContext)

  // Request preview when card becomes visible
  useEffect(() => {
    if (!context || !cardRef.current) return

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            context.requestPreview(pattern.path)
            observer.disconnect() // Only need to load once
          }
        })
      },
      { rootMargin: '100px' } // Start loading slightly before visible
    )

    observer.observe(cardRef.current)

    return () => observer.disconnect()
  }, [pattern.path, context])

  const previewUrl = context?.previews[pattern.path]?.image_data || null

  return (
    <button
      ref={cardRef}
      onClick={onClick}
      className={`group flex flex-col items-center gap-2 p-2 rounded-lg transition-all duration-200 ease-out hover:-translate-y-1 hover:scale-[1.02] hover:shadow-lg hover:bg-accent/30 active:scale-95 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 ${
        isSelected ? 'ring-2 ring-primary ring-offset-2 ring-offset-background bg-accent/20' : ''
      }`}
    >
      <div className="relative w-full aspect-square">
        <div className="w-full h-full rounded-full overflow-hidden border bg-muted">
          {previewUrl && !imageError ? (
            <>
              {!imageLoaded && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="material-icons-outlined animate-spin text-xl text-muted-foreground">
                    sync
                  </span>
                </div>
              )}
              <img
                src={previewUrl}
                alt={pattern.name}
                className={`w-full h-full object-cover pattern-preview transition-opacity ${
                  imageLoaded ? 'opacity-100' : 'opacity-0'
                }`}
                loading="lazy"
                onLoad={() => setImageLoaded(true)}
                onError={() => setImageError(true)}
              />
            </>
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <span className="material-icons-outlined text-2xl text-muted-foreground">
                {imageError ? 'broken_image' : 'image'}
              </span>
            </div>
          )}
        </div>
        {/* Favorite heart button */}
        <div
          className={`absolute -top-1 -right-1 w-6 h-6 rounded-full flex items-center justify-center shadow-sm z-10 transition-opacity duration-200 cursor-pointer bg-white/90 dark:bg-gray-800/90 ${
            isFavorite ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
          }`}
          onClick={(e) => onToggleFavorite(pattern.path, e)}
          title={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
        >
          <span
            className={`material-icons transition-colors ${
              isFavorite ? 'text-red-500 hover:text-red-600' : 'text-gray-400 hover:text-red-500'
            }`}
            style={{ fontSize: '14px' }}
          >
            {isFavorite ? 'favorite' : 'favorite_border'}
          </span>
        </div>
      </div>

      <span className="text-xs font-medium text-center truncate w-full px-1" title={pattern.name}>
        {pattern.name}
      </span>
    </button>
  )
}
