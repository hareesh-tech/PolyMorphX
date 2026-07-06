#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void printHeader() {
    printf("================================\n");
    printf("||           AND               ||\n");
    printf("================================\n");
}

int main() {
    int a, b;
    char command[10]; // To store the quit command

    // Print the heading panel
    printHeader();

    while (1) { // Infinite loop to keep prompting for input
        // Prompt the user for input
        printf("Enter first integer: ");
        if (scanf("%s", command) == 1) {
            // Check if the user wants to quit
            if (strcmp(command, "quit") == 0 || strcmp(command, "exit") == 0) {
                break;
            }
            a = atoi(command); // Convert to integer
        }

        printf("Enter second integer: ");
        scanf("%d", &b);

        // Perform AND operation
        int result = a & b;

        // Print the result
        printf("The result of %d AND %d is: %d\n\n", a, b, result);
    }

    return 0;
}
