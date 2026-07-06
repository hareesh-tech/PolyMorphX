#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <winsock2.h>

#pragma comment(lib, "ws2_32.lib") // Link with ws2_32.lib

#define PORT 8080
#define SERVER "127.0.0.1"
#define BUFFER_SIZE 1024

int main() {
    WSADATA wsaData;
    SOCKET sock;
    struct sockaddr_in serverAddr;
    char buffer[BUFFER_SIZE];

    // Initialize Winsock
    WSAStartup(MAKEWORD(2, 2), &wsaData);

    // Create socket
    sock = socket(AF_INET, SOCK_STREAM, 0);

    serverAddr.sin_family = AF_INET;
    serverAddr.sin_addr.s_addr = inet_addr(SERVER);
    serverAddr.sin_port = htons(PORT);

    // Connect to server
    connect(sock, (struct sockaddr *)&serverAddr, sizeof(serverAddr));

    // Chat loop
    while (1) {
        printf("You: ");
        fgets(buffer, BUFFER_SIZE, stdin);
        send(sock, buffer, strlen(buffer), 0);

        if (strcmp(buffer, "quit\n") == 0) {
            printf("Disconnecting...\n");
            break;
        }

        memset(buffer, 0, BUFFER_SIZE);
        recv(sock, buffer, BUFFER_SIZE, 0);
        printf("Server: %s", buffer);
    }

    // Cleanup
    closesocket(sock);
    WSACleanup();
    return 0;
}
