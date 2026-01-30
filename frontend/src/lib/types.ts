// Shared types across pages

export interface PatternMetadata {
  path: string
  name: string
  category: string
  date_modified: number
  coordinates_count: number
}

export interface PreviewData {
  image_data: string
  first_coordinate: { x: number; y: number } | null
  last_coordinate: { x: number; y: number } | null
  error?: string
}

export interface Playlist {
  name: string
  files: string[]
}

export type SortOption = 'name' | 'date' | 'size' | 'favorites'
export type PreExecution = 'none' | 'adaptive' | 'clear_from_in' | 'clear_from_out' | 'clear_sideway'
export type RunMode = 'single' | 'indefinite'

export const preExecutionOptions: { value: PreExecution; label: string }[] = [
  { value: 'adaptive', label: 'Adaptive' },
  { value: 'clear_from_in', label: 'Clear From Center' },
  { value: 'clear_from_out', label: 'Clear From Perimeter' },
  { value: 'clear_sideway', label: 'Clear Sideways' },
  { value: 'none', label: 'None' },
]
