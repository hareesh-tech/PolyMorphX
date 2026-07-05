#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main() {
    int a, b;
    char operation[4]; // To store the operation string
    char command[10];  // To store the quit command

    while (1) { // Infinite loop to keep prompting for input
        // Prompt the user for input
        printf("Enter first integer : ");
        if (scanf("%s", command) == 1) {
            // Check if the user wants to quit
            if (strcmp(command, "quit") == 0 || strcmp(command, "exit") == 0) {
                break;
            }
            a = atoi(command); // Convert to integer
        }

        printf("Enter second integer: ");
        scanf("%d", &b);

        printf("Enter operation (add, sub, mul, div): ");
        scanf("%3s", operation); // Read a string with maximum length of 3

        int result = 0;

        // Determine the operation
        if (strcmp(operation, "+") == 0 || strcmp(operation, "add") == 0) {
            result = a + b;
        } else if (strcmp(operation, "-") == 0 || strcmp(operation, "sub") == 0) {
            result = a - b;
        } else if (strcmp(operation, "*") == 0 || strcmp(operation, "mul") == 0) {
            result = a * b;
        } else if (strcmp(operation, "/") == 0 || strcmp(operation, "div") == 0) {
            if (b == 0) {
                printf("Error: Division by zero!\n");
                continue; // Skip this iteration
            }
            result = a / b;
        } else {
            printf("Invalid operation! Use add, sub, mul, or div.\n");
            continue; // Skip to the next iteration
        }

        // Print the result
        printf("The result of %d %s %d is: %d\n", a, operation, b, result);
    }

    return 0;
}
