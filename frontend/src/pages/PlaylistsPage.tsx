import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useOutletContext } from 'react-router-dom'
import { toast } from 'sonner'
import { Trash2 } from 'lucide-react'
import { apiClient } from '@/lib/apiClient'
import {
  initPreviewCacheDB,
  getPreviewsFromCache,
  savePreviewToCache,
} from '@/lib/previewCache'
import { fuzzyMatch } from '@/lib/utils'
import { useOnBackendConnected } from '@/hooks/useBackendConnection'
import type { PatternMetadata, PreviewData, SortOption, PreExecution, RunMode } from '@/lib/types'
import { preExecutionOptions } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import type { DragEndEvent } from '@dnd-kit/core'
import {
  SortableContext,
  arrayMove,
  rectSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

export function PlaylistsPage() {
  const { isPlayOnlyActive } = useOutletContext<{ isPlayOnlyActive?: boolean }>() || {}

  // Playlists state
  const [playlists, setPlaylists] = useState<string[]>([])
  const [selectedPlaylist, setSelectedPlaylist] = useState<string | null>(() => {
    return localStorage.getItem('playlist-selected')
  })
  const [playlistPatterns, setPlaylistPatterns] = useState<string[]>([])
  const [isLoadingPlaylists, setIsLoadingPlaylists] = useState(true)

  // All patterns for the picker modal
  const [allPatterns, setAllPatterns] = useState<PatternMetadata[]>([])
  const [allPatternHistories, setAllPatternHistories] = useState<Record<string, {
    play_count: number
    last_played: string | null
  }>>({})
  const [previews, setPreviews] = useState<Record<string, PreviewData>>({})

  // Pattern picker modal state
  const [isPickerOpen, setIsPickerOpen] = useState(false)
  const [selectedPatternPaths, setSelectedPatternPaths] = useState<Set<string>>(new Set())
  // Selection snapshot taken when the picker opens — used to detect unsaved changes
  const initialPickerSelectionRef = useRef<Set<string>>(new Set())
  const [showDiscardConfirm, setShowDiscardConfirm] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  const [sortBy, setSortBy] = useState<SortOption>('name')
  const [sortAsc, setSortAsc] = useState(true)

  // Favorites state (loaded from "Favorites" playlist)
  const [favorites, setFavorites] = useState<Set<string>>(new Set())

  // Create/Rename playlist modal
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [isRenameModalOpen, setIsRenameModalOpen] = useState(false)
  const [newPlaylistName, setNewPlaylistName] = useState('')
  const [playlistToRename, setPlaylistToRename] = useState<string | null>(null)

  // Guards create/rename/save-patterns confirm buttons against double-submit
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Delete confirmation dialog
  const [playlistToDelete, setPlaylistToDelete] = useState<string | null>(null)

  // Mobile view state - show content panel when a playlist is selected
  const [mobileShowContent, setMobileShowContent] = useState(false)

  // Swipe gesture to go back on mobile
  const swipeTouchStartRef = useRef<{ x: number; y: number } | null>(null)
  const handleSwipeTouchStart = (e: React.TouchEvent) => {
    swipeTouchStartRef.current = {
      x: e.touches[0].clientX,
      y: e.touches[0].clientY,
    }
  }
  const handleSwipeTouchEnd = (e: React.TouchEvent) => {
    if (!swipeTouchStartRef.current || !mobileShowContent) return
    const deltaX = e.changedTouches[0].clientX - swipeTouchStartRef.current.x
    const deltaY = e.changedTouches[0].clientY - swipeTouchStartRef.current.y

    // Swipe right to go back (positive X, more horizontal than vertical)
    if (deltaX > 80 && deltaX > Math.abs(deltaY)) {
      setMobileShowContent(false)
    }
    swipeTouchStartRef.current = null
  }

  // Playback settings - initialized from localStorage
  const [runMode, setRunMode] = useState<RunMode>(() => {
    const cached = localStorage.getItem('playlist-runMode')
    return (cached === 'single' || cached === 'indefinite') ? cached : 'single'
  })
  const [shuffle, setShuffle] = useState(() => {
    return localStorage.getItem('playlist-shuffle') === 'true'
  })
  const [pauseTime, setPauseTime] = useState(() => {
    const cached = localStorage.getItem('playlist-pauseTime')
    return cached ? Number(cached) : 5
  })
  const [pauseUnit, setPauseUnit] = useState<'sec' | 'min' | 'hr' | 'per_day'>(() => {
    const cached = localStorage.getItem('playlist-pauseUnit')
    return (cached === 'sec' || cached === 'min' || cached === 'hr' || cached === 'per_day') ? cached : 'min'
  })
  const [clearPattern, setClearPattern] = useState<PreExecution>(() => {
    const cached = localStorage.getItem('preExecution')
    return (cached as PreExecution) || 'adaptive'
  })

  // Persist playback settings to localStorage
  useEffect(() => {
    localStorage.setItem('playlist-runMode', runMode)
  }, [runMode])
  useEffect(() => {
    localStorage.setItem('playlist-shuffle', String(shuffle))
  }, [shuffle])
  useEffect(() => {
    localStorage.setItem('playlist-pauseTime', String(pauseTime))
  }, [pauseTime])
  useEffect(() => {
    localStorage.setItem('playlist-pauseUnit', pauseUnit)
  }, [pauseUnit])
  useEffect(() => {
    localStorage.setItem('preExecution', clearPattern)
  }, [clearPattern])

  // Persist selected playlist to localStorage
  useEffect(() => {
    if (selectedPlaylist) {
      localStorage.setItem('playlist-selected', selectedPlaylist)
    } else {
      localStorage.removeItem('playlist-selected')
    }
  }, [selectedPlaylist])

  // Validate cached playlist exists and load its patterns after playlists load
  const initialLoadDoneRef = useRef(false)
  useEffect(() => {
    if (isLoadingPlaylists) return

    if (selectedPlaylist) {
      if (playlists.includes(selectedPlaylist)) {
        // Load patterns for cached playlist on initial load only
        if (!initialLoadDoneRef.current) {
          initialLoadDoneRef.current = true
          fetchPlaylistPatterns(selectedPlaylist)
        }
      } else {
        // Cached playlist no longer exists
        setSelectedPlaylist(null)
      }
    }
  }, [isLoadingPlaylists, playlists, selectedPlaylist])

  // Close modals when playback starts
  useEffect(() => {
    const handlePlaybackStarted = () => {
      setIsPickerOpen(false)
      setIsCreateModalOpen(false)
      setIsRenameModalOpen(false)
    }
    window.addEventListener('playback-started', handlePlaybackStarted)
    return () => window.removeEventListener('playback-started', handlePlaybackStarted)
  }, [])
  const [isRunning, setIsRunning] = useState(false)

  // Convert pause time to seconds based on unit.
  // For 'per_day', value is "plays per day" so the interval between starts
  // is 86400 / N seconds.
  const getPauseTimeInSeconds = () => {
    switch (pauseUnit) {
      case 'per_day':
        return Math.floor(86400 / Math.max(1, pauseTime))
      case 'hr':
        return pauseTime * 3600
      case 'min':
        return pauseTime * 60
      default:
        return pauseTime
    }
  }

  // Preview loading
  const pendingPreviewsRef = useRef<Set<string>>(new Set())
  const batchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Mirror of `previews` so requestPreview stays identity-stable — see
  // BrowsePage: depending on the state would churn every observer per load
  const previewsRef = useRef(previews)
  useEffect(() => {
    previewsRef.current = previews
  }, [previews])
  const abortControllerRef = useRef<AbortController | null>(null)

  // Initialize and fetch data
  useEffect(() => {
    initPreviewCacheDB().catch(() => {})
    fetchPlaylists()
    fetchAllPatterns()
    loadFavorites()

    // Cleanup on unmount: abort in-flight requests and clear pending queue
    return () => {
      if (batchTimeoutRef.current) {
        clearTimeout(batchTimeoutRef.current)
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
      pendingPreviewsRef.current.clear()
    }
  }, [])

  // Refetch when backend reconnects
  useOnBackendConnected(() => {
    fetchPlaylists()
    fetchAllPatterns()
    loadFavorites()
  })

  const fetchPlaylists = async () => {
    setIsLoadingPlaylists(true)
    try {
      const data = await apiClient.get<string[]>('/list_all_playlists')
      // Backend returns array directly, not { playlists: [...] }
      setPlaylists(Array.isArray(data) ? data : [])
    } catch (error) {
      console.error('Error fetching playlists:', error)
      toast.error('Failed to load playlists')
    } finally {
      setIsLoadingPlaylists(false)
    }
  }

  const fetchPlaylistPatterns = async (name: string) => {
    try {
      const data = await apiClient.get<{ files: string[] }>(`/get_playlist?name=${encodeURIComponent(name)}`)
      setPlaylistPatterns(data.files || [])

      // Previews are now lazy-loaded via IntersectionObserver in LazyPatternPreview
    } catch (error) {
      console.error('Error fetching playlist:', error)
      toast.error('Failed to load playlist')
      setPlaylistPatterns([])
    }
  }

  const fetchAllPatterns = async () => {
    try {
      const [data, historyData] = await Promise.all([
        apiClient.get<PatternMetadata[]>('/list_theta_rho_files_with_metadata'),
        apiClient.get<Record<string, { play_count: number; last_played: string | null }>>('/api/pattern_history_all')
      ])
      setAllPatterns(data)
      setAllPatternHistories(historyData)
    } catch (error) {
      console.error('Error fetching patterns:', error)
    }
  }

  // Load favorites from "Favorites" playlist
  const loadFavorites = async () => {
    try {
      const playlist = await apiClient.get<{ files?: string[] }>('/get_playlist?name=Favorites')
      setFavorites(new Set(playlist.files || []))
    } catch {
      // Favorites playlist doesn't exist yet - that's OK
    }
  }

  // Preview loading functions (similar to BrowsePage)
  const loadPreviewsForPaths = async (paths: string[]) => {
    const cachedPreviews = await getPreviewsFromCache(paths)

    if (cachedPreviews.size > 0) {
      const cachedData: Record<string, PreviewData> = {}
      cachedPreviews.forEach((previewData, path) => {
        cachedData[path] = previewData
      })
      setPreviews(prev => ({ ...prev, ...cachedData }))
    }

    const uncached = paths.filter(p => !cachedPreviews.has(p))
    if (uncached.length > 0) {
      fetchPreviewsBatch(uncached)
    }
  }

  const fetchPreviewsBatch = async (paths: string[]) => {
    const BATCH_SIZE = 10 // Process 10 patterns at a time to avoid overwhelming the backend

    // Create new AbortController for this batch of requests
    abortControllerRef.current = new AbortController()
    const signal = abortControllerRef.current.signal

    // Process in batches
    for (let i = 0; i < paths.length; i += BATCH_SIZE) {
      // Check if aborted before each batch
      if (signal.aborted) break

      const batch = paths.slice(i, i + BATCH_SIZE)

      try {
        const data = await apiClient.post<Record<string, PreviewData>>('/preview_thr_batch', { file_names: batch }, signal)

        const newPreviews: Record<string, PreviewData> = {}
        for (const [path, previewData] of Object.entries(data)) {
          newPreviews[path] = previewData as PreviewData
          // Only cache valid previews (with image_data and no error)
          if (previewData && !(previewData as PreviewData).error) {
            savePreviewToCache(path, previewData as PreviewData)
          }
        }
        setPreviews(prev => ({ ...prev, ...newPreviews }))
      } catch (error) {
        // Stop processing if aborted, otherwise continue with next batch
        if (error instanceof Error && error.name === 'AbortError') break
        console.error('Error fetching previews batch:', error)
      }

      // Small delay between batches to reduce backend load
      if (i + BATCH_SIZE < paths.length) {
        await new Promise((resolve) => setTimeout(resolve, 100))
      }
    }
  }

  const requestPreview = useCallback((path: string) => {
    if (previewsRef.current[path] || pendingPreviewsRef.current.has(path)) return

    pendingPreviewsRef.current.add(path)

    if (batchTimeoutRef.current) {
      clearTimeout(batchTimeoutRef.current)
    }

    batchTimeoutRef.current = setTimeout(() => {
      const pathsToFetch = Array.from(pendingPreviewsRef.current)
      pendingPreviewsRef.current.clear()
      if (pathsToFetch.length > 0) {
        loadPreviewsForPaths(pathsToFetch)
      }
    }, 100)
  }, [])

  // Playlist CRUD operations
  const handleSelectPlaylist = (name: string) => {
    setSelectedPlaylist(name)
    fetchPlaylistPatterns(name)
    setMobileShowContent(true) // Show content panel on mobile
  }

  // Go back to playlist list on mobile
  const handleMobileBack = () => {
    setMobileShowContent(false)
  }

  const handleCreatePlaylist = async () => {
    if (isSubmitting) return
    if (!newPlaylistName.trim()) {
      toast.error('Please enter a playlist name')
      return
    }

    const name = newPlaylistName.trim()
    setIsSubmitting(true)
    try {
      await apiClient.post('/create_playlist', { playlist_name: name, files: [] })
      toast.success('Playlist created')
      setIsCreateModalOpen(false)
      setNewPlaylistName('')
      await fetchPlaylists()
      handleSelectPlaylist(name)
    } catch (error) {
      console.error('Create playlist error:', error)
      toast.error(error instanceof Error ? error.message : 'Failed to create playlist')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleRenamePlaylist = async () => {
    if (isSubmitting) return
    if (!playlistToRename || !newPlaylistName.trim()) return

    setIsSubmitting(true)
    try {
      await apiClient.post('/rename_playlist', { old_name: playlistToRename, new_name: newPlaylistName.trim() })
      toast.success('Playlist renamed')
      setIsRenameModalOpen(false)
      setNewPlaylistName('')
      setPlaylistToRename(null)
      fetchPlaylists()
      if (selectedPlaylist === playlistToRename) {
        setSelectedPlaylist(newPlaylistName.trim())
      }
    } catch (error) {
      toast.error('Failed to rename playlist')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeletePlaylist = async (name: string) => {
    try {
      await apiClient.delete('/delete_playlist', { playlist_name: name })
      toast.success('Playlist deleted')
      fetchPlaylists()
      if (selectedPlaylist === name) {
        setSelectedPlaylist(null)
        setPlaylistPatterns([])
      }
    } catch (error) {
      toast.error('Failed to delete playlist')
    }
  }

  const handleRemovePattern = async (patternPath: string) => {
    if (!selectedPlaylist) return

    const newPatterns = playlistPatterns.filter(p => p !== patternPath)
    try {
      await apiClient.post('/modify_playlist', { playlist_name: selectedPlaylist, files: newPatterns })
      setPlaylistPatterns(newPatterns)
      toast.success('Pattern removed')
    } catch (error) {
      toast.error('Failed to remove pattern')
    }
  }

  // Drag-and-drop sensors for reordering playlist patterns
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // Require 8px movement before starting drag
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  // Reorder patterns within the selected playlist and persist immediately
  const handlePatternDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event
    if (!selectedPlaylist || !over || active.id === over.id) return

    // Sortable ids are `${path}-${index}` (paths may repeat in a playlist)
    const ids = playlistPatterns.map((p, i) => `${p}-${i}`)
    const oldIndex = ids.indexOf(active.id.toString())
    const newIndex = ids.indexOf(over.id.toString())
    if (oldIndex === -1 || newIndex === -1) return

    const previousPatterns = playlistPatterns
    const newPatterns = arrayMove(playlistPatterns, oldIndex, newIndex)
    setPlaylistPatterns(newPatterns)
    try {
      await apiClient.post('/modify_playlist', { playlist_name: selectedPlaylist, files: newPatterns })
    } catch (error) {
      // Roll back the optimistic reorder on failure
      setPlaylistPatterns(previousPatterns)
      toast.error('Failed to reorder playlist')
    }
  }

  // Pattern picker modal
  const openPatternPicker = () => {
    setSelectedPatternPaths(new Set(playlistPatterns))
    initialPickerSelectionRef.current = new Set(playlistPatterns)
    setSearchQuery('')
    setIsPickerOpen(true)
    // Previews are lazy-loaded via IntersectionObserver in LazyPatternPreview
  }

  // Closing the picker (cancel, escape, overlay click) with unsaved selection
  // changes prompts for confirmation instead of silently discarding them
  const handlePickerOpenChange = (open: boolean) => {
    if (!open) {
      const initial = initialPickerSelectionRef.current
      const hasChanges =
        selectedPatternPaths.size !== initial.size ||
        Array.from(selectedPatternPaths).some((p) => !initial.has(p))
      if (hasChanges) {
        setShowDiscardConfirm(true)
        return
      }
    }
    setIsPickerOpen(open)
  }

  const handleSavePatterns = async () => {
    if (isSubmitting) return
    if (!selectedPlaylist) return

    // Preserve the existing playlist order — Set insertion order would move a
    // deselected-then-reselected pattern to the end. Keep surviving patterns
    // in place and append only genuinely new selections.
    const newPatterns = [
      ...playlistPatterns.filter((p) => selectedPatternPaths.has(p)),
      ...Array.from(selectedPatternPaths).filter((p) => !playlistPatterns.includes(p)),
    ]
    setIsSubmitting(true)
    try {
      await apiClient.post('/modify_playlist', { playlist_name: selectedPlaylist, files: newPatterns })
      setPlaylistPatterns(newPatterns)
      setIsPickerOpen(false)
      toast.success('Playlist updated')
      // Previews are lazy-loaded via IntersectionObserver
    } catch (error) {
      toast.error('Failed to update playlist')
    } finally {
      setIsSubmitting(false)
    }
  }

  const togglePatternSelection = (path: string) => {
    setSelectedPatternPaths(prev => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }

  // Run playlist
  const handleRunPlaylist = async () => {
    if (!selectedPlaylist || playlistPatterns.length === 0) return

    setIsRunning(true)
    try {
      await apiClient.post('/run_playlist', {
        playlist_name: selectedPlaylist,
        run_mode: runMode === 'indefinite' ? 'indefinite' : 'single',
        pause_time: getPauseTimeInSeconds(),
        clear_pattern: clearPattern,
        shuffle: shuffle,
        pause_from_start: pauseUnit === 'per_day',
      })
      toast.success(`Started playlist: ${selectedPlaylist}`)
      // Trigger Now Playing bar to open
      window.dispatchEvent(new CustomEvent('playback-started'))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to run playlist')
    } finally {
      setIsRunning(false)
    }
  }

  // Filter and sort patterns for picker
  const categories = useMemo(() => {
    const cats = new Set(allPatterns.map(p => p.category))
    return ['all', ...Array.from(cats).sort()]
  }, [allPatterns])

  const filteredPatterns = useMemo(() => {
    let filtered = allPatterns

    if (searchQuery) {
      filtered = filtered.filter(p => fuzzyMatch(p.name, searchQuery))
    }

    if (selectedCategory !== 'all') {
      filtered = filtered.filter(p => p.category === selectedCategory)
    }

    filtered = [...filtered].sort((a, b) => {
      let cmp = 0
      switch (sortBy) {
        case 'name':
          cmp = a.name.localeCompare(b.name)
          break
        case 'date':
          cmp = a.date_modified - b.date_modified
          break
        case 'size':
          cmp = a.coordinates_count - b.coordinates_count
          break
        case 'favorites': {
          const aFav = favorites.has(a.path) ? 1 : 0
          const bFav = favorites.has(b.path) ? 1 : 0
          cmp = bFav - aFav // Favorites first
          if (cmp === 0) {
            cmp = a.name.localeCompare(b.name) // Then by name
          }
          break
        }
        case 'plays': {
          const aKey = a.path.split('/').pop() || ''
          const bKey = b.path.split('/').pop() || ''
          const aPlays = allPatternHistories[aKey]?.play_count ?? 0
          const bPlays = allPatternHistories[bKey]?.play_count ?? 0
          cmp = aPlays - bPlays
          if (cmp === 0) {
            cmp = a.name.localeCompare(b.name)
          }
          break
        }
        case 'last_played': {
          const aKey = a.path.split('/').pop() || ''
          const bKey = b.path.split('/').pop() || ''
          const aTime = allPatternHistories[aKey]?.last_played || ''
          const bTime = allPatternHistories[bKey]?.last_played || ''
          cmp = aTime.localeCompare(bTime)
          if (cmp === 0) {
            cmp = a.name.localeCompare(b.name)
          }
          break
        }
      }
      return sortAsc ? cmp : -cmp
    })

    return filtered
  }, [allPatterns, searchQuery, selectedCategory, sortBy, sortAsc, favorites, allPatternHistories])

  // Get pattern name from path
  const getPatternName = (path: string) => {
    const pattern = allPatterns.find(p => p.path === path)
    return pattern?.name || path.split('/').pop()?.replace('.thr', '') || path
  }

  // Get preview URL (backend already returns full data URL)
  const getPreviewUrl = (path: string) => {
    const preview = previews[path]
    return preview?.image_data || null
  }

  // Copy for the delete-confirmation dialog. Pattern count is only known for
  // the selected playlist (and Favorites, which is loaded separately) — omit
  // it gracefully otherwise.
  const deletePatternCount =
    playlistToDelete !== null && playlistToDelete === selectedPlaylist
      ? playlistPatterns.length
      : playlistToDelete === 'Favorites'
        ? favorites.size
        : null
  const deleteDescription = [
    deletePatternCount !== null
      ? `This playlist contains ${deletePatternCount} pattern${deletePatternCount === 1 ? '' : 's'}. This cannot be undone.`
      : 'This cannot be undone.',
    playlistToDelete === 'Favorites'
      ? 'This is your Favorites list — deleting it also clears all hearted patterns.'
      : null,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className="flex flex-col w-full max-w-5xl mx-auto gap-4 sm:gap-6 py-3 sm:py-6 px-0 sm:px-4 overflow-hidden" style={{ height: 'calc(100dvh - 14rem - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px))' }}>
      {/* Page Header */}
      <div className="space-y-0.5 sm:space-y-1 shrink-0 pl-1">
        <h1 className="text-xl font-semibold tracking-tight">Playlists</h1>
        <p className="text-xs text-muted-foreground">
          Create and manage pattern playlists
        </p>
      </div>

      <Separator className="shrink-0" />

      {/* Main Content Area */}
      <div className="flex flex-col lg:flex-row gap-4 flex-1 min-h-0 relative overflow-hidden">
        {/* Playlists Sidebar - Full screen on mobile, sidebar on desktop */}
        <aside className={`w-full lg:w-64 shrink-0 bg-card border rounded-lg flex flex-col h-full overflow-hidden transition-transform duration-300 ease-in-out ${
          mobileShowContent ? '-translate-x-full lg:translate-x-0 absolute lg:relative inset-0 lg:inset-auto' : 'translate-x-0'
        }`}>
          <div className="flex items-center justify-between px-3 py-2.5 border-b shrink-0">
            <div>
              <h2 className="text-lg font-semibold">My Playlists</h2>
              <p className="text-sm text-muted-foreground">{playlists.length} playlist{playlists.length !== 1 ? 's' : ''}</p>
            </div>
            {!isPlayOnlyActive && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                aria-label="Create playlist"
                onClick={() => {
                  setNewPlaylistName('')
                  setIsCreateModalOpen(true)
                }}
              >
                <span aria-hidden="true" className="material-icons-outlined text-xl">add</span>
              </Button>
            )}
          </div>

          <nav className="flex-1 overflow-y-auto p-2 space-y-1 min-h-0">
          {isLoadingPlaylists ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <span className="text-sm">Loading...</span>
            </div>
          ) : playlists.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground gap-2">
              <span aria-hidden="true" className="material-icons-outlined text-3xl">playlist_add</span>
              <span className="text-sm">No playlists yet</span>
            </div>
          ) : (
            playlists.map(name => (
              <div
                key={name}
                className={`group flex items-center justify-between rounded-lg transition-colors ${
                  selectedPlaylist === name
                    ? 'bg-accent text-accent-foreground'
                    : 'hover:bg-muted text-muted-foreground'
                }`}
              >
                <button
                  type="button"
                  className="flex items-center gap-2 min-w-0 flex-1 w-full text-left px-3 py-2 cursor-pointer rounded-lg"
                  onClick={() => handleSelectPlaylist(name)}
                >
                  <span aria-hidden="true" className="material-icons-outlined text-lg">playlist_play</span>
                  <span className="truncate text-sm font-medium">{name}</span>
                </button>
                {!isPlayOnlyActive && (
                  <div className="flex items-center gap-1 pr-2 opacity-100 pointer-fine:opacity-0 pointer-fine:group-hover:opacity-100 pointer-fine:group-focus-within:opacity-100 transition-opacity">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="h-7 w-7"
                      aria-label={`Rename playlist ${name}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        setPlaylistToRename(name)
                        setNewPlaylistName(name)
                        setIsRenameModalOpen(true)
                      }}
                    >
                      <span aria-hidden="true" className="material-icons-outlined text-base">edit</span>
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="h-7 w-7 text-destructive hover:text-destructive hover:bg-destructive/20"
                      aria-label={`Delete playlist ${name}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        setPlaylistToDelete(name)
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                )}
              </div>
            ))
          )}
        </nav>
      </aside>

        {/* Main Content - Slides in from right on mobile, swipe right to go back */}
        <main
          className={`flex-1 bg-card border rounded-lg flex flex-col overflow-hidden min-h-0 relative transition-transform duration-300 ease-in-out ${
            mobileShowContent ? 'translate-x-0' : 'translate-x-full lg:translate-x-0 absolute lg:relative inset-0 lg:inset-auto'
          }`}
          onTouchStart={handleSwipeTouchStart}
          onTouchEnd={handleSwipeTouchEnd}
        >
          {/* Header */}
          <header className="flex items-center justify-between px-3 py-2.5 border-b shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              {/* Back button - mobile only */}
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 lg:hidden shrink-0"
                aria-label="Back to playlists"
                onClick={handleMobileBack}
              >
                <span aria-hidden="true" className="material-icons-outlined">arrow_back</span>
              </Button>
              <div className="min-w-0">
                <h2 className="text-lg font-semibold truncate">
                  {selectedPlaylist || 'Select a Playlist'}
                </h2>
                {selectedPlaylist && playlistPatterns.length > 0 && (
                  <p className="text-sm text-muted-foreground">
                    {playlistPatterns.length} pattern{playlistPatterns.length !== 1 ? 's' : ''}
                  </p>
                )}
              </div>
            </div>
            {!isPlayOnlyActive && (
              <Button
                onClick={openPatternPicker}
                disabled={!selectedPlaylist}
                size="sm"
                className="gap-2"
              >
                <span aria-hidden="true" className="material-icons-outlined text-base">add</span>
                <span className="hidden sm:inline">Add Patterns</span>
              </Button>
            )}
          </header>

          {/* Patterns List */}
          <div className={`flex-1 overflow-y-auto p-4 min-h-0 ${selectedPlaylist ? 'pb-28 sm:pb-24' : ''}`}>
            {!selectedPlaylist ? (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3">
                <div className="p-4 rounded-full bg-muted">
                  <span aria-hidden="true" className="material-icons-outlined text-5xl">touch_app</span>
                </div>
                <div className="text-center">
                  <p className="font-medium">No playlist selected</p>
                  <p className="text-sm">Select a playlist from the sidebar to view its patterns</p>
                </div>
              </div>
            ) : playlistPatterns.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3">
                <div className="p-4 rounded-full bg-muted">
                  <span aria-hidden="true" className="material-icons-outlined text-5xl">library_music</span>
                </div>
                <div className="text-center">
                  <p className="font-medium">Empty playlist</p>
                  <p className="text-sm">Add patterns to get started</p>
                </div>
                {!isPlayOnlyActive && (
                  <Button variant="secondary" className="mt-2 gap-2" onClick={openPatternPicker}>
                    <span aria-hidden="true" className="material-icons-outlined text-base">add</span>
                    Add Patterns
                  </Button>
                )}
              </div>
            ) : (
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={handlePatternDragEnd}
              >
                <SortableContext
                  items={playlistPatterns.map((path, index) => `${path}-${index}`)}
                  strategy={rectSortingStrategy}
                >
                  <div className="grid grid-cols-4 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3 sm:gap-4">
                    {playlistPatterns.map((path, index) => (
                      <SortablePlaylistPattern
                        key={`${path}-${index}`}
                        id={`${path}-${index}`}
                        path={path}
                        name={getPatternName(path)}
                        previewUrl={getPreviewUrl(path)}
                        requestPreview={requestPreview}
                        canEdit={!isPlayOnlyActive}
                        onRemove={() => handleRemovePattern(path)}
                      />
                    ))}
                  </div>
                </SortableContext>
              </DndContext>
            )}
          </div>

          {/* Floating Playback Controls */}
          {selectedPlaylist && (
            <div className="absolute bottom-0 left-0 right-0 pointer-events-none z-20">
              {/* Blur backdrop */}
              <div className="h-20 bg-gradient-to-t" />

              {/* Controls container */}
              <div className="absolute bottom-4 left-0 right-0 flex items-center justify-center gap-3 px-4 pointer-events-auto">
                {/* Control pill */}
                <div className="flex items-center h-12 sm:h-14 bg-card rounded-full shadow-xl border px-1.5 sm:px-2">
                  {/* Shuffle & Loop */}
                  <div className="flex items-center px-1 sm:px-2 border-r border-border gap-0.5 sm:gap-1">
                    <button
                      onClick={() => setShuffle(!shuffle)}
                      className={`w-9 h-9 sm:w-10 sm:h-10 rounded-full flex items-center justify-center transition ${
                        shuffle
                          ? 'text-primary bg-primary/10'
                          : 'text-muted-foreground hover:bg-muted'
                      }`}
                      title="Shuffle"
                      aria-label="Shuffle"
                      aria-pressed={shuffle}
                    >
                      <span aria-hidden="true" className="material-icons-outlined text-lg sm:text-xl">shuffle</span>
                    </button>
                    <button
                      onClick={() => setRunMode(runMode === 'indefinite' ? 'single' : 'indefinite')}
                      className={`w-9 h-9 sm:w-10 sm:h-10 rounded-full flex items-center justify-center transition ${
                        runMode === 'indefinite'
                          ? 'text-primary bg-primary/10'
                          : 'text-muted-foreground hover:bg-muted'
                      }`}
                      title={runMode === 'indefinite' ? 'Loop mode' : 'Play once mode'}
                      aria-label="Loop playlist"
                      aria-pressed={runMode === 'indefinite'}
                    >
                      <span aria-hidden="true" className="material-icons-outlined text-lg sm:text-xl">repeat</span>
                    </button>
                  </div>

                  {/* Pause Time */}
                  <div className="flex items-center px-2 sm:px-3 gap-2 sm:gap-3 border-r border-border">
                    <span className="text-[10px] sm:text-xs font-semibold text-muted-foreground tracking-wider hidden sm:block">Pause</span>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="secondary"
                        size="icon"
                        className="w-7 h-7 sm:w-8 sm:h-8"
                        aria-label="Decrease pause time"
                        onClick={() => {
                          const step = pauseUnit === 'hr' ? 0.5 : 1
                          // 'per_day' is plays-per-day, so it must stay >= 1.
                          const min = pauseUnit === 'per_day' ? 1 : 0
                          setPauseTime(Math.max(min, pauseTime - step))
                        }}
                      >
                        <span aria-hidden="true" className="material-icons-outlined text-sm">remove</span>
                      </Button>
                      <button
                        onClick={() => {
                          const units: ('sec' | 'min' | 'hr' | 'per_day')[] = ['sec', 'min', 'hr', 'per_day']
                          const currentIndex = units.indexOf(pauseUnit)
                          const nextUnit = units[(currentIndex + 1) % units.length]
                          // Switching into per_day with a 0 value would mean "0 plays/day" — bump to 1.
                          if (nextUnit === 'per_day' && pauseTime < 1) {
                            setPauseTime(1)
                          }
                          setPauseUnit(nextUnit)
                        }}
                        className="relative flex items-center justify-center min-w-14 sm:min-w-16 px-1 text-xs sm:text-sm font-bold hover:text-primary transition"
                        title={pauseUnit === 'per_day' ? 'Plays per day (timed from pattern start). Click to change unit.' : 'Click to change unit'}
                        aria-label={`Pause unit: ${pauseUnit}. Activate to change unit`}
                      >
                        {pauseUnit === 'per_day'
                          ? `${pauseTime}/day`
                          : `${pauseTime}${pauseUnit === 'sec' ? 's' : pauseUnit === 'min' ? 'm' : 'h'}`}
                        <span aria-hidden="true" className="material-icons-outlined text-xs opacity-50 scale-75 ml-0.5">swap_vert</span>
                      </button>
                      <Button
                        variant="secondary"
                        size="icon"
                        className="w-7 h-7 sm:w-8 sm:h-8"
                        aria-label="Increase pause time"
                        onClick={() => {
                          const step = pauseUnit === 'hr' ? 0.5 : 1
                          // Cap per_day at 24 (one start every hour) — beyond that the cadence
                          // collides with typical pattern run durations.
                          const max = pauseUnit === 'per_day' ? 24 : Number.POSITIVE_INFINITY
                          setPauseTime(Math.min(max, pauseTime + step))
                        }}
                      >
                        <span aria-hidden="true" className="material-icons-outlined text-sm">add</span>
                      </Button>
                    </div>
                  </div>

                  {/* Clear Pattern Dropdown */}
                  <div className="flex items-center px-1 sm:px-2">
                    <Select value={clearPattern} onValueChange={(v) => setClearPattern(v as PreExecution)}>
                      <SelectTrigger aria-label="Clear pattern option" className={`w-9 h-9 sm:w-10 sm:h-10 rounded-full border-0 p-0 shadow-none focus:ring-0 justify-center [&>svg]:hidden transition ${
                        clearPattern !== 'none' ? '!bg-primary/10' : '!bg-transparent hover:!bg-muted'
                      }`}>
                        <span aria-hidden="true" className={`material-icons-outlined text-lg sm:text-xl ${
                          clearPattern !== 'none' ? 'text-primary' : 'text-muted-foreground'
                        }`}>cleaning_services</span>
                      </SelectTrigger>
                      <SelectContent className="max-w-[min(22rem,calc(100vw-2.5rem))]">
                        {preExecutionOptions.map(opt => (
                          <SelectItem key={opt.value} value={opt.value}>
                            <div>
                              <div>{opt.label}</div>
                              {/* Descriptions overwhelm small screens — labels only there */}
                              <div className="hidden sm:block text-xs text-muted-foreground font-normal">
                                {opt.description}
                              </div>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {/* Play Button */}
                <button
                  onClick={handleRunPlaylist}
                  disabled={isRunning || playlistPatterns.length === 0}
                  className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-primary hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground text-primary-foreground shadow-lg shadow-primary/30 hover:shadow-primary/50 hover:scale-105 disabled:shadow-none disabled:hover:scale-100 transition-all duration-200 flex items-center justify-center"
                  title="Run Playlist"
                  aria-label="Run playlist"
                >
                  {isRunning ? (
                    <span aria-hidden="true" className="material-icons-outlined text-xl sm:text-2xl animate-spin">sync</span>
                  ) : (
                    <span aria-hidden="true" className="material-icons text-xl sm:text-2xl ml-0.5">play_arrow</span>
                  )}
                </button>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Create Playlist Modal */}
      <Dialog open={isCreateModalOpen} onOpenChange={setIsCreateModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <span aria-hidden="true" className="material-icons-outlined text-primary">playlist_add</span>
              Create New Playlist
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="playlistName">Playlist Name</Label>
              <Input
                id="playlistName"
                value={newPlaylistName}
                onChange={(e) => setNewPlaylistName(e.target.value)}
                placeholder="e.g., Favorites, Morning Patterns..."
                onKeyDown={(e) => e.key === 'Enter' && handleCreatePlaylist()}
                autoFocus
              />
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="secondary" onClick={() => setIsCreateModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreatePlaylist} disabled={isSubmitting} className="gap-2">
              <span aria-hidden="true" className="material-icons-outlined text-base">add</span>
              Create Playlist
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rename Playlist Modal */}
      <Dialog open={isRenameModalOpen} onOpenChange={setIsRenameModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <span aria-hidden="true" className="material-icons-outlined text-primary">edit</span>
              Rename Playlist
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="renamePlaylist">New Name</Label>
              <Input
                id="renamePlaylist"
                value={newPlaylistName}
                onChange={(e) => setNewPlaylistName(e.target.value)}
                placeholder="Enter new name"
                onKeyDown={(e) => e.key === 'Enter' && handleRenamePlaylist()}
                autoFocus
              />
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="secondary" onClick={() => setIsRenameModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleRenamePlaylist} disabled={isSubmitting} className="gap-2">
              <span aria-hidden="true" className="material-icons-outlined text-base">save</span>
              Save Name
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Pattern Picker Modal */}
      <Dialog open={isPickerOpen} onOpenChange={handlePickerOpenChange}>
        <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <span aria-hidden="true" className="material-icons-outlined text-primary">playlist_add</span>
              Add Patterns to {selectedPlaylist}
            </DialogTitle>
          </DialogHeader>

          {/* Search and Filters */}
          <div className="space-y-3 py-2">
            <div className="relative">
              <span aria-hidden="true" className="material-icons-outlined absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-lg">
                search
              </span>
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search patterns..."
                className="pl-10 pr-10 h-10"
              />
              {searchQuery && (
                <button
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  aria-label="Clear search"
                  onClick={() => setSearchQuery('')}
                >
                  <span aria-hidden="true" className="material-icons-outlined text-lg">close</span>
                </button>
              )}
            </div>

            <div className="flex flex-wrap gap-2 items-center">
              {/* Folder dropdown - icon only on mobile, with text on sm+ */}
              <Select value={selectedCategory} onValueChange={setSelectedCategory}>
                <SelectTrigger className="h-9 w-9 sm:w-auto rounded-full bg-card border-border shadow-sm text-sm px-0 sm:px-3 justify-center sm:justify-between [&>svg]:hidden sm:[&>svg]:block [&>span:last-of-type]:hidden sm:[&>span:last-of-type]:inline gap-2">
                  <span aria-hidden="true" className="material-icons-outlined text-lg shrink-0">folder</span>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {categories.map(cat => (
                    <SelectItem key={cat} value={cat}>
                      {cat === 'all' ? 'All Folders' : cat}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Sort dropdown - icon only on mobile, with text on sm+ */}
              <Select value={sortBy} onValueChange={(v) => setSortBy(v as SortOption)}>
                <SelectTrigger className="h-9 w-9 sm:w-auto rounded-full bg-card border-border shadow-sm text-sm px-0 sm:px-3 justify-center sm:justify-between [&>svg]:hidden sm:[&>svg]:block [&>span:last-of-type]:hidden sm:[&>span:last-of-type]:inline gap-2">
                  <span aria-hidden="true" className="material-icons-outlined text-lg shrink-0">sort</span>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="favorites">Favorites</SelectItem>
                  <SelectItem value="name">Name</SelectItem>
                  <SelectItem value="date">Modified</SelectItem>
                  <SelectItem value="size">Size</SelectItem>
                  <SelectItem value="plays">Most Played</SelectItem>
                  <SelectItem value="last_played">Last Played</SelectItem>
                </SelectContent>
              </Select>

              {/* Sort direction - pill shaped */}
              <Button
                variant="outline"
                size="icon"
                className="h-9 w-9 rounded-full bg-card shadow-sm"
                onClick={() => setSortAsc(!sortAsc)}
                title={sortAsc ? 'Ascending' : 'Descending'}
              >
                <span aria-hidden="true" className="material-icons-outlined text-lg">
                  {sortAsc ? 'arrow_upward' : 'arrow_downward'}
                </span>
              </Button>

              <div className="flex-1" />

              {/* Select All / Deselect All toggle */}
              <Button
                variant="outline"
                size="sm"
                className="h-9 rounded-full bg-card shadow-sm text-sm gap-1.5"
                onClick={() => {
                  const allFilteredPaths = filteredPatterns.map(p => p.path)
                  const allSelected = allFilteredPaths.every(p => selectedPatternPaths.has(p))
                  setSelectedPatternPaths(prev => {
                    const next = new Set(prev)
                    if (allSelected) {
                      allFilteredPaths.forEach(p => next.delete(p))
                    } else {
                      allFilteredPaths.forEach(p => next.add(p))
                    }
                    return next
                  })
                }}
              >
                <span aria-hidden="true" className="material-icons-outlined text-base">
                  {filteredPatterns.length > 0 && filteredPatterns.every(p => selectedPatternPaths.has(p.path)) ? 'deselect' : 'select_all'}
                </span>
                <span className="hidden sm:inline">
                  {filteredPatterns.length > 0 && filteredPatterns.every(p => selectedPatternPaths.has(p.path)) ? 'Deselect All' : 'Select All'}
                </span>
              </Button>

              {/* Selection count - compact on mobile */}
              <div className="flex items-center gap-1 sm:gap-2 text-sm bg-card rounded-full px-2 sm:px-3 py-2 shadow-sm border">
                <span aria-hidden="true" className="material-icons-outlined text-base text-primary">check_circle</span>
                <span className="font-medium">{selectedPatternPaths.size}</span>
                <span className="hidden sm:inline text-muted-foreground">selected</span>
              </div>
            </div>
          </div>

          {/* Patterns Grid */}
          <div className="flex-1 overflow-y-auto border rounded-lg p-4 min-h-[300px] bg-muted/20">
            {filteredPatterns.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3">
                <div className="p-4 rounded-full bg-muted">
                  <span aria-hidden="true" className="material-icons-outlined text-5xl">search_off</span>
                </div>
                <span className="text-sm">No patterns found</span>
              </div>
            ) : (
              <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-4">
                {filteredPatterns.map(pattern => {
                  const isSelected = selectedPatternPaths.has(pattern.path)
                  return (
                    <div
                      key={pattern.path}
                      role="checkbox"
                      aria-checked={isSelected}
                      tabIndex={0}
                      className="flex flex-col items-center gap-2 cursor-pointer"
                      onClick={() => togglePatternSelection(pattern.path)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          togglePatternSelection(pattern.path)
                        }
                      }}
                    >
                      <div
                        className={`relative w-full aspect-square rounded-full overflow-hidden border-2 bg-muted transition-all ${
                          isSelected
                            ? 'border-primary ring-2 ring-primary/20'
                            : 'border-transparent hover:border-muted-foreground/30'
                        }`}
                      >
                        <LazyPatternPreview
                          path={pattern.path}
                          previewUrl={getPreviewUrl(pattern.path)}
                          requestPreview={requestPreview}
                          alt={pattern.name}
                        />
                        {isSelected && (
                          <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-primary flex items-center justify-center shadow-md">
                            <span aria-hidden="true" className="material-icons text-primary-foreground" style={{ fontSize: '14px' }}>
                              check
                            </span>
                          </div>
                        )}
                      </div>
                      <p className={`text-xs truncate font-medium w-full text-center ${isSelected ? 'text-primary' : ''}`}>
                        {pattern.name}
                      </p>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="secondary" onClick={() => handlePickerOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={handleSavePatterns} disabled={isSubmitting} className="gap-2">
              <span aria-hidden="true" className="material-icons-outlined text-base">save</span>
              Save Selection
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Playlist Confirmation */}
      <ConfirmDialog
        open={playlistToDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPlaylistToDelete(null)
        }}
        title={`Delete "${playlistToDelete ?? ''}"?`}
        description={deleteDescription}
        confirmLabel="Delete"
        destructive
        onConfirm={() => {
          if (playlistToDelete) handleDeletePlaylist(playlistToDelete)
        }}
      />

      {/* Discard Picker Selection Confirmation */}
      <ConfirmDialog
        open={showDiscardConfirm}
        onOpenChange={setShowDiscardConfirm}
        title="Discard selection changes?"
        description="Your unsaved pattern selection changes will be lost."
        confirmLabel="Discard"
        destructive
        onConfirm={() => {
          setShowDiscardConfirm(false)
          setIsPickerOpen(false)
        }}
      />
    </div>
  )
}

// Sortable pattern card for drag-to-reorder within the selected playlist
interface SortablePlaylistPatternProps {
  id: string
  path: string
  name: string
  previewUrl: string | null
  requestPreview: (path: string) => void
  canEdit: boolean
  onRemove: () => void
}

function SortablePlaylistPattern({
  id,
  path,
  name,
  previewUrl,
  requestPreview,
  canEdit,
  onRemove,
}: SortablePlaylistPatternProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 1000 : 'auto',
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="flex flex-col items-center gap-1.5 sm:gap-2 group"
    >
      <div className="relative w-full aspect-square">
        <div className="w-full h-full rounded-full overflow-hidden border bg-muted hover:ring-2 hover:ring-primary hover:ring-offset-2 hover:ring-offset-background transition-all cursor-pointer">
          <LazyPatternPreview
            path={path}
            previewUrl={previewUrl}
            requestPreview={requestPreview}
            alt={name}
          />
        </div>
        {canEdit && (
          <>
            {/* Drag handle */}
            <div
              {...attributes}
              {...listeners}
              className="absolute -top-0.5 -left-0.5 sm:-top-1 sm:-left-1 w-5 h-5 rounded-full bg-card border flex items-center justify-center opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity shadow-sm z-10 cursor-grab active:cursor-grabbing touch-none"
              aria-label={`Reorder ${name}`}
            >
              <span aria-hidden="true" className="material-icons-outlined text-muted-foreground" style={{ fontSize: '12px' }}>drag_indicator</span>
            </div>
            <button
              className="absolute -top-0.5 -right-0.5 sm:-top-1 sm:-right-1 w-5 h-5 rounded-full bg-destructive hover:bg-destructive/90 text-destructive-foreground flex items-center justify-center opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity shadow-sm z-10"
              onClick={onRemove}
              title="Remove from playlist"
            >
              <span aria-hidden="true" className="material-icons" style={{ fontSize: '12px' }}>close</span>
            </button>
          </>
        )}
      </div>
      <p className="text-[10px] sm:text-xs truncate font-medium w-full text-center">{name}</p>
    </div>
  )
}

// Lazy-loading pattern preview component
interface LazyPatternPreviewProps {
  path: string
  previewUrl: string | null
  requestPreview: (path: string) => void
  alt: string
  className?: string
}

function LazyPatternPreview({ path, previewUrl, requestPreview, alt, className = '' }: LazyPatternPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const hasRequestedRef = useRef(false)

  useEffect(() => {
    if (!containerRef.current || previewUrl || hasRequestedRef.current) return

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && !hasRequestedRef.current) {
            hasRequestedRef.current = true
            requestPreview(path)
            observer.disconnect()
          }
        })
      },
      { rootMargin: '100px' }
    )

    observer.observe(containerRef.current)

    return () => observer.disconnect()
  }, [path, previewUrl, requestPreview])

  return (
    <div ref={containerRef} className={`w-full h-full flex items-center justify-center ${className}`}>
      {previewUrl ? (
        <img
          src={previewUrl}
          alt={alt}
          loading="lazy"
          className="w-full h-full object-cover pattern-preview"
        />
      ) : (
        <span aria-hidden="true" className="material-icons-outlined text-muted-foreground text-sm sm:text-base">
          image
        </span>
      )}
    </div>
  )
}
