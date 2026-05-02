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

export type SortOption = 'name' | 'date' | 'size' | 'favorites' | 'plays' | 'last_played'
export type PreExecution = 'none' | 'adaptive' | 'clear_from_in' | 'clear_from_out' | 'clear_sideway'
export type RunMode = 'single' | 'indefinite' | 'scheduled'

export const preExecutionOptions: { value: PreExecution; label: string; description: string }[] = [
  { value: 'adaptive', label: 'Adaptive', description: 'Automatically picks the best clear direction based on where the ball is' },
  { value: 'clear_from_in', label: 'From Center', description: 'Spirals outward from the center to erase the current pattern' },
  { value: 'clear_from_out', label: 'From Perimeter', description: 'Spirals inward from the edge to erase the current pattern' },
  { value: 'clear_sideway', label: 'Sideways', description: 'Sweeps side-to-side across the sand to erase the current pattern' },
  { value: 'none', label: 'None', description: 'Start drawing immediately without clearing the sand first' },
]
