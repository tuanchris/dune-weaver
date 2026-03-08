import { useState } from 'react'
import { HexColorPicker } from 'react-colorful'
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
      <PopoverContent className="w-auto p-3" align="start">
        <HexColorPicker color={value} onChange={onChange} />
        <div className="flex flex-wrap gap-1.5 mt-3 max-w-[200px]">
          {presets.map((preset) => (
            <button
              key={preset}
              type="button"
              className={cn(
                'w-6 h-6 rounded-full border-2 cursor-pointer transition-transform hover:scale-110',
                value.toLowerCase() === preset.toLowerCase()
                  ? 'border-foreground scale-110'
                  : 'border-transparent'
              )}
              style={{ backgroundColor: preset }}
              onClick={() => onChange(preset)}
            />
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}
