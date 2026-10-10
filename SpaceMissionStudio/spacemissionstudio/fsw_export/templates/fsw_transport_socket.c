/*
 ISC License

 Copyright (c) 2026, Autonomous Vehicle Systems Lab, University of Colorado at Boulder

 Permission to use, copy, modify, and/or distribute this software for any
 purpose with or without fee is hereby granted, provided that the above
 copyright notice and this permission notice appear in all copies.

 THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
*/

/*
 * Socket transport for the SIL contract (fsw_transport.h): a Unix-domain
 * socket on Linux and macOS, TCP on the loopback interface everywhere
 * (Windows: Winsock). The simulation listens; this side connects.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fsw_transport.h"

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
typedef SOCKET FswSocket;
#define FSW_BAD_SOCKET INVALID_SOCKET
#define fswCloseSocket closesocket
#else
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
typedef int FswSocket;
#define FSW_BAD_SOCKET (-1)
#define fswCloseSocket close
#endif

#ifdef MSG_NOSIGNAL
#define FSW_SEND_FLAGS MSG_NOSIGNAL
#else
#define FSW_SEND_FLAGS 0
#endif

static int socketSend(FswTransport *transport, const void *data, size_t size)
{
    const char *at = (const char *)data;
    FswSocket s = (FswSocket)transport->handle;
    while (size > 0) {
        int chunk = size > 65536 ? 65536 : (int)size;
        int sent = (int)send(s, at, chunk, FSW_SEND_FLAGS);
        if (sent <= 0) {
#ifndef _WIN32
            if (sent < 0 && errno == EINTR) {
                continue;
            }
#endif
            return -1;
        }
        at += sent;
        size -= (size_t)sent;
    }
    return 0;
}

static int socketReceive(FswTransport *transport, void *data, size_t size)
{
    char *at = (char *)data;
    FswSocket s = (FswSocket)transport->handle;
    while (size > 0) {
        int chunk = size > 65536 ? 65536 : (int)size;
        int got = (int)recv(s, at, chunk, 0);
        if (got <= 0) {
#ifndef _WIN32
            if (got < 0 && errno == EINTR) {
                continue;
            }
#endif
            return -1;
        }
        at += got;
        size -= (size_t)got;
    }
    return 0;
}

static void socketClose(FswTransport *transport)
{
    if ((FswSocket)transport->handle != FSW_BAD_SOCKET) {
        fswCloseSocket((FswSocket)transport->handle);
        transport->handle = (long long)FSW_BAD_SOCKET;
    }
#ifdef _WIN32
    WSACleanup();
#endif
}

static int connectTcp(const char *hostPort, FswSocket *out, char *error, size_t errorSize)
{
    char host[64];
    const char *colon = strrchr(hostPort, ':');
    struct sockaddr_in where;
    long port;
    int one = 1;
    FswSocket s;
    if (colon == NULL || (size_t)(colon - hostPort) >= sizeof host) {
        snprintf(error, errorSize, "tcp address \"%s\" is not host:port", hostPort);
        return -1;
    }
    memcpy(host, hostPort, (size_t)(colon - hostPort));
    host[colon - hostPort] = '\0';
    port = strtol(colon + 1, NULL, 10);
    if (port <= 0 || port > 65535) {
        snprintf(error, errorSize, "tcp port \"%s\" is not 1-65535", colon + 1);
        return -1;
    }
    if (strcmp(host, "127.0.0.1") != 0) {
        snprintf(error, errorSize, "the SIL link only uses the loopback address 127.0.0.1, not \"%s\"", host);
        return -1;
    }
    memset(&where, 0, sizeof where);
    where.sin_family = AF_INET;
    where.sin_port = htons((unsigned short)port);
    where.sin_addr.s_addr = htonl(0x7F000001UL);
    s = socket(AF_INET, SOCK_STREAM, 0);
    if (s == FSW_BAD_SOCKET) {
        snprintf(error, errorSize, "cannot create a TCP socket");
        return -1;
    }
    setsockopt(s, IPPROTO_TCP, TCP_NODELAY, (const char *)&one, sizeof one);
    if (connect(s, (struct sockaddr *)&where, sizeof where) != 0) {
        snprintf(error, errorSize, "cannot connect to 127.0.0.1:%ld", port);
        fswCloseSocket(s);
        return -1;
    }
    *out = s;
    return 0;
}

#ifndef _WIN32
static int connectUnix(const char *path, FswSocket *out, char *error, size_t errorSize)
{
    struct sockaddr_un where;
    FswSocket s;
    if (strlen(path) >= sizeof where.sun_path) {
        snprintf(error, errorSize, "socket path is longer than %u bytes", (unsigned)(sizeof where.sun_path - 1));
        return -1;
    }
    memset(&where, 0, sizeof where);
    where.sun_family = AF_UNIX;
    memcpy(where.sun_path, path, strlen(path) + 1);
    s = socket(AF_UNIX, SOCK_STREAM, 0);
    if (s == FSW_BAD_SOCKET) {
        snprintf(error, errorSize, "cannot create a Unix-domain socket");
        return -1;
    }
    if (connect(s, (struct sockaddr *)&where, sizeof where) != 0) {
        snprintf(error, errorSize, "cannot connect to %s", path);
        close(s);
        return -1;
    }
    *out = s;
    return 0;
}
#endif

int fsw_transport_connect(FswTransport *transport, const char *address, char *error, size_t errorSize)
{
    FswSocket s = FSW_BAD_SOCKET;
    int status;
#ifdef _WIN32
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        snprintf(error, errorSize, "cannot start Winsock");
        return -1;
    }
#endif
    if (strncmp(address, "tcp:", 4) == 0) {
        status = connectTcp(address + 4, &s, error, errorSize);
    } else if (strncmp(address, "unix:", 5) == 0) {
#ifdef _WIN32
        snprintf(error, errorSize, "Unix-domain sockets are not used on Windows; use a tcp: address");
        status = -1;
#else
        status = connectUnix(address + 5, &s, error, errorSize);
#endif
    } else {
        snprintf(error, errorSize, "address \"%s\" is neither unix:<path> nor tcp:127.0.0.1:<port>", address);
        status = -1;
    }
    if (status != 0) {
#ifdef _WIN32
        WSACleanup();
#endif
        return -1;
    }
#ifdef SO_NOSIGPIPE
    {
        int one = 1;
        setsockopt(s, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof one);
    }
#endif
    transport->send = socketSend;
    transport->receive = socketReceive;
    transport->close = socketClose;
    transport->handle = (long long)s;
    return 0;
}
