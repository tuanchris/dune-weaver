#include <AccelStepper.h>
#include <MultiStepper.h>
#include <math.h> // For M_PI and mathematical operations

#define rotInterfaceType AccelStepper::DRIVER
#define inOutInterfaceType AccelStepper::DRIVER

#define stepPin_rot 2
#define dirPin_rot 5
#define stepPin_InOut 3
#define dirPin_InOut 6

#define rot_total_steps 16000.0
#define inOut_total_steps 5760.0
#define gearRatio 10

#define BUFFER_SIZE 10 // Maximum number of theta-rho pairs in a batch

#define buttonPin 11 // Z- signal pin on the CNC shield
#define pot1 A1      // Potentiometer 1, Abort pin on the CNC shield
#define pot2 A0      // Potentiometer 2, Hold pint on the CNC shield

#define MODE_APP 0
#define MODE_SPIROGRAPH 1

// Create stepper motor objects
AccelStepper rotStepper(rotInterfaceType, stepPin_rot, dirPin_rot);
AccelStepper inOutStepper(inOutInterfaceType, stepPin_InOut, dirPin_InOut);

// Create a MultiStepper object
MultiStepper multiStepper;

// Buffer for storing theta-rho pairs
float buffer[BUFFER_SIZE][2]; // Store theta, rho pairs
int bufferCount = 0;          // Number of pairs in the buffer
bool batchComplete = false;

// Track the current position in polar coordinates
float currentTheta = 0.0; // Current theta in radians
float currentRho = 0.0;   // Current rho (0 to 1)
bool isFirstCoordinates = true;
float totalRevolutions = 0.0; // Tracks cumulative revolutions
float maxSpeed = 5000;
float maxAcceleration = 5000;
long interpolationResolution = 0.001;
float userDefinedSpeed = maxSpeed; // Store user-defined speed

// Running Mode
int currentMode = MODE_APP; // Default mode is app mode.

// FIRMWARE VERSION
const char* firmwareVersion = "1.4.0";
const char* motorType = "DRV8825";

void setup()
{
    // Set maximum speed and acceleration
    rotStepper.setMaxSpeed(maxSpeed);     // Adjust as needed
    rotStepper.setAcceleration(maxAcceleration); // Adjust as needed

    inOutStepper.setMaxSpeed(maxSpeed);     // Adjust as needed
    inOutStepper.setAcceleration(maxAcceleration); // Adjust as needed

    // Add steppers to MultiStepper
    multiStepper.addStepper(rotStepper);
    multiStepper.addStepper(inOutStepper);

    // Configure the buttons and potentiometers for Spirograph mode
    pinMode(buttonPin, INPUT_PULLUP); // Configure button pin with internal pull-up
    pinMode(A0, INPUT); // Potentiometer 1 input
    pinMode(A1, INPUT); // Potentiometer 2 input

    // Initialize serial communication
    Serial.begin(115200);
    Serial.println("Table: Dune Weaver");
    Serial.println("Drivers: DRV8825");
    Serial.println("Version: 1.4.0");
    Serial.println("R");
    homing();
}

void resetTheta()
{
    isFirstCoordinates = true; // Set flag to skip interpolation for the next movement
    Serial.println("THETA_RESET"); // Notify Python
}

void loop() {
    updateModeSwitch(); // Check and handle mode switching

    // Call the appropriate mode function based on the current mode
    if (currentMode == MODE_SPIROGRAPH) {
        spirographMode();
    } else if (currentMode == MODE_APP) {
        appMode();
    }
}

void updateModeSwitch() {
    // Read the current state of the latching switch
    bool currentSwitchState = digitalRead(buttonPin);
    int newMode = currentSwitchState == LOW ? MODE_SPIROGRAPH : MODE_APP;

    if (newMode != currentMode) {
        handleModeChange(newMode); // Handle mode-specific transitions
        currentMode = newMode; // Update the current mode
    }
}

void handleModeChange(int newMode) {
    // Print mode switch information
    if (newMode == MODE_SPIROGRAPH) {
        Serial.println("Spirograph Mode Active");
        rotStepper.setMaxSpeed(userDefinedSpeed * 0.5); // Use 50% of user-defined speed
        inOutStepper.setMaxSpeed(userDefinedSpeed * 0.5);
        isFirstCoordinates = false;
    } else if (newMode == MODE_APP) {
        Serial.println("App Mode Active");
        rotStepper.setMaxSpeed(userDefinedSpeed); // Restore user-defined speed
        inOutStepper.setMaxSpeed(userDefinedSpeed);
        resetTheta();
    }

    movePolar(currentTheta, 0); // Move to the center
}

void spirographMode() {
    static float currentFrequency = 2.95; // Track the current frequency (default value)
    static float phaseShift = 0.0;       // Track the phase shift for smooth transitions

    // Read potentiometer for frequency adjustment
    int pot1Value = analogRead(pot1);
    float newFrequency = mapFloat(pot1Value, 0, 1023, 0.5, 6); // Map to range
    newFrequency = round(newFrequency * 10) / 10.0;            // Round to one decimal place

    // Force the value to x.95 or x.10 to have a slight variation each revolution
    if (fmod(newFrequency, 1.0) >= 0.5) {
        newFrequency = floor(newFrequency) + 0.95; // Round up to x.95
    } else {
        newFrequency = floor(newFrequency) + 0.10; // Round down to x.10
    }

    // Adjust phase shift if frequency changes
    if (newFrequency != currentFrequency) {
        phaseShift += currentTheta * (currentFrequency - newFrequency);
        currentFrequency = newFrequency; // Update the current frequency
    }

    // Read variation knob to adjust the minimum rho
    int pot2Value = analogRead(pot2);
    float minRho = round(mapFloat(pot2Value, 0, 1023, 0, 0.5) * 20) / 20.0; // Minimum rho in steps of 0.05

    // Calculate amplitude and offset for the sine wave
    float amplitude = (1.0 - minRho) / 2.0; // Half of the oscillation range
    float offset = minRho + amplitude;      // Center the wave within the range [minRho, 1]

    // Calculate the next target theta
    float stepSize = maxSpeed * (2 * M_PI / rot_total_steps) / 10; // Smaller steps for finer control
    float nextTheta = currentTheta + stepSize;

    // Count total revolutions
    totalRevolutions = (nextTheta / (2 * M_PI));

    // Calculate rho using the adjusted sine wave with phase shift
    currentRho = offset + amplitude * cos((currentTheta * currentFrequency) + phaseShift);
    float nextRho = offset + amplitude * cos((nextTheta * currentFrequency) + phaseShift);

    // Move the steppers to the calculated position
    movePolar(nextTheta, constrain(nextRho, 0, 1));

    // Update the current theta to the new position
    currentTheta = nextTheta;
}

float mapFloat(long x, long inMin, long inMax, float outMin, float outMax) {
    if (inMax == inMin) {
        Serial.println("Error: mapFloat division by zero");
        return outMin; // Return the minimum output value as a fallback
    }
    return (float)(x - inMin) * (outMax - outMin) / (float)(inMax - inMin) + outMin;
}

void appMode()
{
    // Check for incoming serial commands or theta-rho pairs
    if (Serial.available() > 0)
    {
        String input = Serial.readStringUntil('\n');

        // Ignore invalid messages
        if (input != "HOME" && input != "RESET_THETA" && input != "GET_VERSION" && !input.startsWith("SET_SPEED") && !input.endsWith(";"))
        {
            Serial.print("IGNORED: ");
            Serial.println(input);
            return;
        }

        if (input == "RESET_THETA")
        {
            resetTheta(); // Reset currentTheta
            Serial.println("THETA_RESET"); // Notify Python
            Serial.println("READY");
            return;
        }
        if (input == "HOME")
        {
            homing();
            return;
        }

        // Example: The user calls "SET_SPEED 60" => 60% of maxSpeed
        if (input.startsWith("SET_SPEED"))
        {
            // Parse out the speed value from the command string
            int spaceIndex = input.indexOf(' ');
            if (spaceIndex != -1)
            {
                String speedStr = input.substring(spaceIndex + 1);
                float speedPercentage = speedStr.toFloat();

                // Make sure the percentage is valid
                if (speedPercentage >= 1.0 && speedPercentage <= 100.0)
                {
                    // Convert percentage to actual speed
                    long newSpeed = (speedPercentage / 100.0) * maxSpeed;
                    userDefinedSpeed = newSpeed;

                    // Set the stepper speeds
                    rotStepper.setMaxSpeed(newSpeed);
                    inOutStepper.setMaxSpeed(newSpeed);

                    Serial.println("SPEED_SET");  
                }
                else
                {
                    Serial.println("INVALID_SPEED");
                }
            }
            else
            {
                Serial.println("INVALID_COMMAND");
            }
            return;
        }

        // If not a command, assume it's a batch of theta-rho pairs
        if (!batchComplete)
        {
            int pairIndex = 0;
            int startIdx = 0;

            // Split the batch line into individual theta-rho pairs
            while (pairIndex < BUFFER_SIZE)
            {
                int endIdx = input.indexOf(";", startIdx);
                if (endIdx == -1)
                    break; // No more pairs in the line

                String pair = input.substring(startIdx, endIdx);
                int commaIndex = pair.indexOf(',');

                // Parse theta and rho values
                float theta = pair.substring(0, commaIndex).toFloat(); // Theta in radians
                float rho = pair.substring(commaIndex + 1).toFloat();  // Rho (0 to 1)

                buffer[pairIndex][0] = theta;
                buffer[pairIndex][1] = rho;
                pairIndex++;

                startIdx = endIdx + 1; // Move to next pair
            }
            bufferCount = pairIndex;
            batchComplete = true;
        }
    }

    // Process the buffer if a batch is ready
    if (batchComplete && bufferCount > 0)
    {
        // Start interpolation from the current position
        float startTheta = currentTheta;
        float startRho = currentRho;

        for (int i = 0; i < bufferCount; i++)
        {
            if (isFirstCoordinates)
            {
                // Directly move to the first coordinate of the new pattern
                long initialRotSteps = buffer[0][0] * (rot_total_steps / (2.0 * M_PI));
                rotStepper.setCurrentPosition(initialRotSteps);
                inOutStepper.setCurrentPosition(inOutStepper.currentPosition() - totalRevolutions * rot_total_steps / gearRatio);
                currentTheta = buffer[0][0];
                totalRevolutions = 0;
                isFirstCoordinates = false; // Reset the flag after the first movement
                movePolar(buffer[0][0], buffer[0][1]);
            }
              else
              {
                // Use interpolation for subsequent movements
                interpolatePath(
                    startTheta, startRho,
                    buffer[i][0], buffer[i][1],
                    interpolationResolution
                );
              }
            // Update the starting point for the next segment
            startTheta = buffer[i][0];
            startRho = buffer[i][1];
        }

        batchComplete = false; // Reset batch flag
        bufferCount = 0;       // Clear buffer
        Serial.println("R");
    }
}

void homing()
{
    Serial.println("HOMING");

    // Move inOutStepper inward for homing
    inOutStepper.setSpeed(-maxSpeed); // Adjust speed for homing
    while (true)
    {
        inOutStepper.runSpeed();
        if (inOutStepper.currentPosition() <= -inOut_total_steps * 1.1)
        { // Adjust distance for homing
            break;
        }
    }
    inOutStepper.setCurrentPosition(0); // Set home position
    currentTheta = 0.0;                 // Reset polar coordinates
    currentRho = 0.0;
    Serial.println("HOMED");
}

void movePolar(float theta, float rho)
{
    // Convert polar coordinates to motor steps
    long rotSteps = theta * (rot_total_steps / (2.0 * M_PI)); // Steps for rot axis
    long inOutSteps = rho * inOut_total_steps;                // Steps for in-out axis

    // Calculate offset for inOut axis
    float revolutions = theta / (2.0 * M_PI); // Fractional revolutions (can be positive or negative)
    long offsetSteps = revolutions * rot_total_steps / gearRatio;    // 1600 steps inward or outward per revolution

    // Update the total revolutions to keep track of the offset history
    totalRevolutions += (theta - currentTheta) / (2.0 * M_PI);

    // Apply the offset to the inout axis
    if (!isFirstCoordinates) {
        inOutSteps -= offsetSteps;
    }

    // Define target positions for both motors
    long targetPositions[2];
    targetPositions[0] = rotSteps;
    targetPositions[1] = inOutSteps;

    // Move both motors synchronously
    multiStepper.moveTo(targetPositions);
    multiStepper.runSpeedToPosition(); // Blocking call

    // Update the current coordinates
    currentTheta = theta;
    currentRho = rho;
}

void interpolatePath(float startTheta, float startRho, float endTheta, float endRho, float stepSize)
{
    // Calculate the total distance in the polar coordinate system
    float distance = sqrt(pow(endTheta - startTheta, 2) + pow(endRho - startRho, 2));
    int numSteps = max(1, (int)(distance / stepSize)); // Ensure at least one step

    for (int step = 0; step <= numSteps; step++)
    {
        float t = (float)step / numSteps; // Interpolation factor (0 to 1)
        float interpolatedTheta = startTheta + t * (endTheta - startTheta);
        float interpolatedRho = startRho + t * (endRho - startRho);

        // Move to the interpolated theta-rho
        movePolar(interpolatedTheta, interpolatedRho);
    }
}
