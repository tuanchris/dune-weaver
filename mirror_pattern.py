import sys
import os

def reverse_theta(input_file, output_file):
    # Check if the input file exists
    if not os.path.isfile(input_file):
        print(f"Error: File '{input_file}' not found.")
        return

    # Read the input file and process
    with open(input_file, "r") as infile:
        lines = infile.readlines()

    with open(output_file, "w") as outfile:
        for line in lines:
            # Skip comment lines
            if line.startswith("#"):
                outfile.write(line)
                continue

            # Process lines with theta and rho values
            try:
                theta, rho = map(float, line.split())
                reversed_theta = -theta  # Reverse the sign of theta
                outfile.write(f"{reversed_theta:.5f} {rho:.5f}\n")
            except ValueError:
                # Handle any lines that don't match the expected format
                outfile.write(line)

    print(f"Reversed file saved as: {output_file}")


def main():
    if len(sys.argv) != 3:
        print("Usage: python reverse_theta.py <input_file.thr> <output_file.thr>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    reverse_theta(input_file, output_file)


if __name__ == "__main__":
    main()