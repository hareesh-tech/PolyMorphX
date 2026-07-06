#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <winsock2.h>

#pragma comment(lib, "ws2_32.lib") // Link with ws2_32.lib

#define PORT 8080
#define BUFFER_SIZE 1024

int main() {
    WSADATA wsaData;
    SOCKET serverSocket, clientSocket;
    struct sockaddr_in serverAddr, clientAddr;
    char buffer[BUFFER_SIZE];
    int addrLen = sizeof(clientAddr);

    // Initialize Winsock
    WSAStartup(MAKEWORD(2, 2), &wsaData);

    // Create socket
    serverSocket = socket(AF_INET, SOCK_STREAM, 0);

    serverAddr.sin_family = AF_INET;
    serverAddr.sin_addr.s_addr = INADDR_ANY;
    serverAddr.sin_port = htons(PORT);

    // Bind
    bind(serverSocket, (struct sockaddr *)&serverAddr, sizeof(serverAddr));

    // Listen
    listen(serverSocket, 3);

    printf("Waiting for connections...\n");
    clientSocket = accept(serverSocket, (struct sockaddr *)&clientAddr, &addrLen);
    printf("Client connected\n");

    // Chat loop
    while (1) {
        memset(buffer, 0, BUFFER_SIZE);
        recv(clientSocket, buffer, BUFFER_SIZE, 0);
        printf("Client: %s", buffer);
        
        if (strcmp(buffer, "quit\n") == 0) {
            printf("Client disconnected.\n");
            break;
        }

        printf("You: ");
        fgets(buffer, BUFFER_SIZE, stdin);
        send(clientSocket, buffer, strlen(buffer), 0);
    }

    // Cleanup
    closesocket(clientSocket);
    closesocket(serverSocket);
    WSACleanup();
    return 0;
}
