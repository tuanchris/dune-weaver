#include <AccelStepper.h>
#include <MultiStepper.h>
#include <math.h> // For M_PI and mathematical operations

#define rotInterfaceType AccelStepper::DRIVER
#define inOutInterfaceType AccelStepper::DRIVER

#define ROT_PIN1 14
#define ROT_PIN2 12
#define ROT_PIN3 26
#define ROT_PIN4 27

#define INOUT_PIN1 16
#define INOUT_PIN2 17
#define INOUT_PIN3 18
#define INOUT_PIN4 19


#define rot_total_steps 12800
#define inOut_total_steps 4642
// #define inOut_total_steps 4660
const double gearRatio = 100.0f / 16.0f;

#define BUFFER_SIZE 10 // Maximum number of theta-rho pairs in a batch

// Create stepper motor objects
AccelStepper rotStepper(AccelStepper::FULL4WIRE, ROT_PIN1, ROT_PIN3, ROT_PIN2, ROT_PIN4); // Rot axis
AccelStepper inOutStepper(AccelStepper::FULL4WIRE, INOUT_PIN1, INOUT_PIN3, INOUT_PIN2, INOUT_PIN4); // In-out axis

// Create a MultiStepper object
MultiStepper multiStepper;

// Buffer for storing theta-rho pairs
double buffer[BUFFER_SIZE][2]; // Store theta, rho pairs
int bufferCount = 0;          // Number of pairs in the buffer
bool batchComplete = false;

// Track the current position in polar coordinates
double currentTheta = 0.0; // Current theta in radians
double currentRho = 0.0;   // Current rho (0 to 1)
bool isFirstCoordinates = true;
double totalRevolutions = 0.0; // Tracks cumulative revolutions
double maxSpeed = 500;
double maxAcceleration = 5000;
double subSteps = 1;

int modulus(int x, int y) {
  return x < 0 ? ((x + 1) % y) + y - 1 : x % y;
}

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

void loop()
{
    // Check for incoming serial commands or theta-rho pairs
    if (Serial.available() > 0)
    {
        String input = Serial.readStringUntil('\n');

        // Ignore invalid messages
        if (input != "HOME" && input != "RESET_THETA" && !input.endsWith(";"))
        {
            Serial.println("IGNORED");
            return;
        }

        if (input == "HOME")
        {
            homing();
            return;
        }

        if (input == "RESET_THETA")
        {
            isFirstCoordinates = true;
            currentTheta = 0;
            currentRho = 0;
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
                double theta = pair.substring(0, commaIndex).toDouble(); // Theta in radians
                double rho = pair.substring(commaIndex + 1).toDouble();  // Rho (0 to 1)

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
        rotStepper.enableOutputs();
        inOutStepper.enableOutputs();
        // Start interpolation from the current position
        double startTheta = currentTheta;
        double startRho = currentRho;

        if (isFirstCoordinates) {
          homing();
          isFirstCoordinates = false;
        }

        for (int i = 0; i < bufferCount; i++)
        {
 
            interpolatePath(
                startTheta, startRho,
                buffer[i][0], buffer[i][1],
                subSteps
            );
            // Update the starting point for the next segment
            startTheta = buffer[i][0];
            startRho = buffer[i][1];
        }

        rotStepper.disableOutputs();
        inOutStepper.disableOutputs();
        batchComplete = false; // Reset batch flag
        bufferCount = 0;       // Clear buffer
        Serial.println("R");
    }
}

void homing()
{
    Serial.println("HOMING");
    inOutStepper.enableOutputs();
    // Move inOutStepper inward for homing
    inOutStepper.setSpeed(-maxSpeed); // Adjust speed for homing
    long currentInOut = inOutStepper.currentPosition();
    while (true)
    {
        inOutStepper.runSpeed();
        if (inOutStepper.currentPosition() <= currentInOut - inOut_total_steps * 1.1)
        { // Adjust distance for homing
            break;
        }
    }
    inOutStepper.setCurrentPosition(0); // Set home position
    rotStepper.setCurrentPosition(0);
    currentTheta = 0.0;                 // Reset polar coordinates
    currentRho = 0.0;
    inOutStepper.disableOutputs();
    Serial.println("HOMED");
}


void movePolar(double theta, double rho)
{
    if (rho < 0.0) 
        rho = 0.0;
    else if (rho > 1.0) 
        rho = 1.0;

    long rotSteps = lround(theta * (rot_total_steps / (2.0f * M_PI)));
    double revolutions = theta / (2.0 * M_PI);
    long offsetSteps = lround(revolutions * (rot_total_steps / gearRatio));

    // Now inOutSteps is always derived from the absolute rho, not incrementally
    long inOutSteps = lround(rho * inOut_total_steps);
    
    inOutSteps -= offsetSteps;

    long targetPositions[2] = {rotSteps, inOutSteps};
    multiStepper.moveTo(targetPositions);
    multiStepper.runSpeedToPosition(); // Blocking call

    // Update current coordinates
    currentTheta = theta;
    currentRho = rho;
}

void interpolatePath(double startTheta, double startRho, double endTheta, double endRho, double subSteps)
{
    // Calculate the total distance in the polar coordinate system
    double distance = sqrt(pow(endTheta - startTheta, 2) + pow(endRho - startRho, 2));
    long numSteps = max(1, (int)(distance / subSteps)); // Ensure at least one step
    
    for (long step = 0; step <= numSteps; step++)
    {
        double t = (double)step / numSteps; // Interpolation factor (0 to 1)
        double interpolatedTheta = startTheta + t * (endTheta - startTheta);
        double interpolatedRho = startRho + t * (endRho - startRho);

        // Move to the interpolated theta-rho
        movePolar(interpolatedTheta, interpolatedRho);
    }
}
