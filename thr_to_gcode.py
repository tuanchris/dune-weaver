from math import pi

class State:
    def __init__(self):
        self.current_theta = None  # detect first move
        self.current_rho = 0.0
        self.machine_x = 0.0
        self.machine_y = 0.0
        self.x_steps_per_mm = 320.0
        self.y_steps_per_mm = 530.0
        self.gear_ratio = 10.0
        self.table_type = 'dune_weaver'
        self.speed = 200.0

state = State()

def convert_thr_to_gcode(thr_file_path, output_file_path):
    with open(thr_file_path, 'r') as f:
        lines = f.readlines()

    gcode_lines = ["G21 ; Set units to mm", "G90 ; Absolute positioning"]

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            theta, rho = map(float, stripped.split())
        except ValueError:
            continue

        x_scaling_factor = 2
        y_scaling_factor = 5

        if state.current_theta is None:
            state.current_theta = theta
            delta_theta = 0
        else:
            delta_theta = theta - state.current_theta

        delta_rho = rho - state.current_rho

        x_increment = delta_theta * 100 / (2 * pi * x_scaling_factor)
        y_increment = delta_rho * 100 / y_scaling_factor

        x_total_steps = state.x_steps_per_mm * (100 / x_scaling_factor)
        y_total_steps = state.y_steps_per_mm * (100 / y_scaling_factor)

        offset = x_increment * (x_total_steps * x_scaling_factor / (state.gear_ratio * y_total_steps * y_scaling_factor))
        y_increment += offset

        new_x = state.machine_x + x_increment
        new_y = state.machine_y + y_increment

        gcode_lines.append(f"G1 X{round(new_x, 5)} Y{round(new_y, 5)} F{state.speed}")

        state.machine_x = new_x
        state.machine_y = new_y
        state.current_theta = theta
        state.current_rho = rho

    # Add G92 reset to align with final polar position
    final_rho_mm = state.current_rho * 100 / y_scaling_factor
    gcode_lines.append(f"G92 X0 Y{round(final_rho_mm, 5)}")

    with open(output_file_path, 'w') as f:
        for line in gcode_lines:
            f.write(line + '\n')

    print(f"G-code saved to: {output_file_path}")
    
convert_thr_to_gcode('patterns/clear_from_in_pro.thr', 'patterns/clear_from_in_pro.nc')