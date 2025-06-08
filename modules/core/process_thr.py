#!/usr/bin/env python3
import os
import sys
from pathlib import Path

def process_file(input_path, output_path):
    """Process a single file to remove duplicate consecutive lines and round coordinates."""
    prev = None

    with open(input_path) as f_in, open(output_path, 'w') as f_out:
        for line in f_in:
            line_str = line.strip()
            if not line_str:
                continue

            try:
                parts = line_str.split()
                if len(parts) != 2:
                    continue
                theta = round(float(parts[0]), 3)
                rho = round(float(parts[1]), 3)
                rounded_line = f"{theta:.3f} {rho:.3f}"
            except ValueError:
                continue

            if rounded_line == prev:
                continue

            f_out.write(rounded_line + '\n')
            prev = rounded_line

def process_directory(input_dir, output_dir=None):
    """Recursively process all .thr files in the input directory."""
    input_path = Path(input_dir)

    if output_dir is None:
        output_path = input_path / 'processed'
    else:
        output_path = Path(output_dir)

    output_path.mkdir(parents=True, exist_ok=True)

    thr_files = list(input_path.rglob('*.thr'))

    if not thr_files:
        print(f"No .thr files found in {input_dir}")
        return

    print(f"Found {len(thr_files)} .thr files to process")

    for thr_file in thr_files:
        relative_path = thr_file.relative_to(input_path)
        output_file = output_path / relative_path
        output_file.parent.mkdir(parents=True, exist_ok=True)

        print(f"Processing {thr_file} -> {output_file}")
        process_file(thr_file, output_file)

    print(f"\nProcessing complete! Processed files are in: {output_path}")

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} input_directory [output_directory]")
        print("If output_directory is not specified, files will be saved in input_directory/processed")
        sys.exit(1)

    input_dir = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.isdir(input_dir):
        print(f"Error: {input_dir} is not a valid directory")
        sys.exit(1)

    process_directory(input_dir, output_dir)

if __name__ == "__main__":
    main()