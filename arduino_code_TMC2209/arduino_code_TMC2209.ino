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
float maxSpeed = 1000;
float maxAcceleration = 50;
long interpolationResolution = 0.001;

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

    // Initialize serial communication
    Serial.begin(115200);
    Serial.println("R");
    homing();
}


void resetTheta()
{
    isFirstCoordinates = true; // Set flag to skip interpolation for the next movement
    Serial.println("THETA_RESET"); // Notify Python
}

void loop()
{
    // Check for incoming serial commands or theta-rho pairs
    if (Serial.available() > 0)
    {
        String input = Serial.readStringUntil('\n');

        // Ignore invalid messages
        if (input != "HOME" && input != "RESET_THETA" && !input.startsWith("SET_SPEED") && !input.endsWith(";"))
        {
            Serial.println("IGNORED");
            return;
        }


        if (input.startsWith("SET_SPEED"))
        {
            // Parse and set the speed
            int spaceIndex = input.indexOf(' ');
            if (spaceIndex != -1)
            {
                String speedStr = input.substring(spaceIndex + 1);
                float speed = speedStr.toFloat();

                if (speed > 0) // Ensure valid speed
                {
                    rotStepper.setMaxSpeed(speed);
                    inOutStepper.setMaxSpeed(speed);
                    Serial.println("SPEED_SET");
                    Serial.println("R");
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

        if (input == "HOME")
        {
            homing();
            return;
        }

        if (input == "RESET_THETA")
        {
            resetTheta(); // Reset currentTheta
            Serial.println("THETA_RESET"); // Notify Python
            Serial.println("R");
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
                inOutStepper.setCurrentPosition(inOutStepper.currentPosition() + (totalRevolutions * rot_total_steps / gearRatio));
                
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
    inOutSteps -= offsetSteps;

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
