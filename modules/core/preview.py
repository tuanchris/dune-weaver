"""Preview module for generating SVG previews of patterns."""
import os
import math
from modules.core.pattern_manager import parse_theta_rho_file, THETA_RHO_DIR

async def generate_preview_svg(pattern_file):
    """Generate an SVG preview for a pattern file."""
    file_path = os.path.join(THETA_RHO_DIR, pattern_file)
    coordinates = parse_theta_rho_file(file_path)
    
    # Convert polar coordinates to SVG path
    svg_path = []
    for i, (theta, rho) in enumerate(coordinates):
        x = 100 - rho * 90 * math.cos(theta)
        y = 100 - rho * 90 * math.sin(theta)
        
        if i == 0:
            svg_path.append(f"M {x:.2f} {y:.2f}")
        else:
            svg_path.append(f"L {x:.2f} {y:.2f}")
    
    svg = f'''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg width="100%" height="100%" viewBox="0 0 200 200" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">
    <path d="{' '.join(svg_path)}" 
          fill="none" 
          stroke="currentColor" 
          stroke-width="0.5"/>
</svg>'''
    
    return svg 