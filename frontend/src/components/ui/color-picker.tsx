import { useState } from 'react'
import { SketchPicker } from 'react-color'
import type { ColorResult } from 'react-color'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface ColorPickerProps {
  value: string
  onChange: (color: string) => void
  className?: string
  presets?: string[]
}

const defaultPresets = [
  '#ff0000', // Red
  '#ff8000', // Orange
  '#ffff00', // Yellow
  '#00ff00', // Green
  '#00ffff', // Cyan
  '#0000ff', // Blue
  '#ff00ff', // Magenta
  '#ffffff', // White
  '#2a9d8f', // Teal
  '#e9c46a', // Sand
  '#dc143c', // Crimson
  '#000000', // Black
]

export function ColorPicker({
  value,
  onChange,
  className,
  presets = defaultPresets,
}: ColorPickerProps) {
  const [open, setOpen] = useState(false)

  const handleChange = (color: ColorResult) => {
    onChange(color.hex)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="secondary"
          className={cn(
            'w-12 h-12 rounded-full p-1 border-2',
            className
          )}
          style={{ backgroundColor: value }}
        >
          <span className="sr-only">Pick a color</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <SketchPicker
          color={value}
          onChange={handleChange}
          presetColors={presets}
          disableAlpha={true}
        />
      </PopoverContent>
    </Popover>
  )
}
