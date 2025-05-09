#include <AccelStepper.h>
#include <math.h> // For mathematical operations

// Stepper driver interface type
#define rotInterfaceType AccelStepper::FULL4WIRE
#define inOutInterfaceType AccelStepper::FULL4WIRE

#define ROT_PIN1 14
#define ROT_PIN2 12
#define ROT_PIN3 26
#define ROT_PIN4 27

#define INOUT_PIN1 16
#define INOUT_PIN2 17
#define INOUT_PIN3 18
#define INOUT_PIN4 19

// Define stepper motor objects
AccelStepper rotStepper(rotInterfaceType, ROT_PIN1, ROT_PIN3, ROT_PIN2, ROT_PIN4);
AccelStepper inOutStepper(inOutInterfaceType, INOUT_PIN1, INOUT_PIN3, INOUT_PIN2, INOUT_PIN4);

// Calibration variables
long rotSteps = 0;   // Steps for the ROT axis
long inOutSteps = 0; // Steps for the INOUT axis

void setup() {
  Serial.begin(115200); // Start serial communication
  Serial.println("Stepper Calibration Tool");

  // Set max speeds and accelerations
  rotStepper.setMaxSpeed(1000);
  rotStepper.setAcceleration(500);

  inOutStepper.setMaxSpeed(1000);
  inOutStepper.setAcceleration(500);

  // Initial message
  Serial.println("Commands:");
  Serial.println(" r <steps> - Move rotation axis by <steps>");
  Serial.println(" i <steps> - Move in-out axis by <steps>");
  Serial.println(" reset r - Reset ROT axis steps to 0");
  Serial.println(" reset i - Reset IN-OUT axis steps to 0");
  Serial.println(" Example: r 200 (moves ROT axis 200 steps)");
}

void loop() {
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n'); // Read user input
    input.trim();

    if (input.length() > 0) {
      if (input.startsWith("reset")) {
        // Reset commands
        char axis = input.charAt(6); // Get the axis to reset ('r' or 'i')

        if (axis == 'r') {
          // Reset ROT axis steps
          rotSteps = 0;
          Serial.println("ROT axis steps reset to 0.");
        } else if (axis == 'i') {
          // Reset IN-OUT axis steps
          inOutSteps = 0;
          Serial.println("IN-OUT axis steps reset to 0.");
        } else {
          Serial.println("Invalid reset command. Use 'reset r' or 'reset i'.");
        }
      } else {
        // Movement commands
        char axis = input.charAt(0);        // First character is the axis
        long steps = input.substring(2).toInt(); // Convert remaining input to steps

        if (axis == 'r') {
          // Move rotation axis
          Serial.print("Moving ROT axis by ");
          Serial.print(steps);
          Serial.println(" steps.");
          rotSteps += steps;
          rotStepper.move(steps);
          while (rotStepper.run()); // Wait for movement to finish
          Serial.print("Current ROT steps: ");
          Serial.println(rotSteps);
        } else if (axis == 'i') {
          // Move in-out axis
          Serial.print("Moving IN-OUT axis by ");
          Serial.print(steps);
          Serial.println(" steps.");
          inOutSteps += steps;
          inOutStepper.move(steps);
          while (inOutStepper.run()); // Wait for movement to finish
          Serial.print("Current IN-OUT steps: ");
          Serial.println(inOutSteps);
        } else {
          Serial.println("Invalid command. Use 'r <steps>' or 'i <steps>'.");
        }
      }
    }
  }
}