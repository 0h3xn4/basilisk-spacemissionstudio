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

/* The SIL contract, version 1, flight-software side (fsw_sil.h, SIL_CONTRACT.md). */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fsw_ports.h"
#include "fsw_scheduler.h"
#include "fsw_sil.h"

#ifdef _WIN32
#include <windows.h>
#else
#include <time.h>
#endif

#define HEADER_SIZE 28u
#define MAX_PAYLOAD (16u * 1024u * 1024u)
#define TOKEN_LENGTH 32u
#define DIGEST_LENGTH 64u

enum { HELLO = 1, HELLO_ACK = 2, RESET = 3, RESET_ACK = 4, STEP = 5, OUTPUT = 6, ERROR_FRAME = 7, BYE = 8 };

typedef struct {
    uint8_t *data;
    size_t size;
    size_t capacity;
} Buffer;

static FswTransport *activeTransport = NULL;
static uint32_t nextSeq = 0;

static uint32_t crc32Of(const uint8_t *data, size_t size)
{
    static uint32_t table[256];
    static int ready = 0;
    uint32_t crc = 0xFFFFFFFFu;
    size_t i;
    if (!ready) {
        uint32_t n, k;
        for (n = 0; n < 256; n++) {
            uint32_t c = n;
            for (k = 0; k < 8; k++) {
                c = (c & 1u) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            }
            table[n] = c;
        }
        ready = 1;
    }
    for (i = 0; i < size; i++) {
        crc = table[(crc ^ data[i]) & 0xFFu] ^ (crc >> 8);
    }
    return crc ^ 0xFFFFFFFFu;
}

static uint64_t monotonicNs(void)
{
#ifdef _WIN32
    LARGE_INTEGER frequency, counter;
    QueryPerformanceFrequency(&frequency);
    QueryPerformanceCounter(&counter);
    return (uint64_t)((double)counter.QuadPart * 1.0e9 / (double)frequency.QuadPart);
#else
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (uint64_t)now.tv_sec * 1000000000ULL + (uint64_t)now.tv_nsec;
#endif
}

static void put16(uint8_t *at, uint32_t v) { at[0] = (uint8_t)v; at[1] = (uint8_t)(v >> 8); }
static void put32(uint8_t *at, uint32_t v) { put16(at, v & 0xFFFFu); put16(at + 2, v >> 16); }
static void put64(uint8_t *at, uint64_t v) { put32(at, (uint32_t)v); put32(at + 4, (uint32_t)(v >> 32)); }
static uint32_t get16(const uint8_t *at) { return (uint32_t)at[0] | ((uint32_t)at[1] << 8); }
static uint32_t get32(const uint8_t *at) { return get16(at) | (get16(at + 2) << 16); }
static uint64_t get64(const uint8_t *at) { return (uint64_t)get32(at) | ((uint64_t)get32(at + 4) << 32); }

static int reserve(Buffer *buffer, size_t size)
{
    if (size > buffer->capacity) {
        uint8_t *grown = (uint8_t *)realloc(buffer->data, size);
        if (grown == NULL) {
            return -1;
        }
        buffer->data = grown;
        buffer->capacity = size;
    }
    return 0;
}

static int append(Buffer *buffer, const void *data, size_t size)
{
    if (reserve(buffer, buffer->size + size) != 0) {
        return -1;
    }
    memcpy(buffer->data + buffer->size, data, size);
    buffer->size += size;
    return 0;
}

static int sendFrame(FswTransport *t, uint32_t type, uint32_t seq, uint64_t timeNs, const uint8_t *payload,
                     size_t size)
{
    uint8_t header[HEADER_SIZE];
    memcpy(header, "SMSL", 4);
    put16(header + 4, FSW_SIL_CONTRACT_VERSION);
    put16(header + 6, type);
    put32(header + 8, seq);
    put32(header + 12, (uint32_t)size);
    put64(header + 16, timeNs);
    put32(header + 24, crc32Of(payload, size));
    if (t->send(t, header, HEADER_SIZE) != 0) {
        return -1;
    }
    return size > 0 ? t->send(t, payload, size) : 0;
}

static void sendError(FswTransport *t, const char *message)
{
    sendFrame(t, ERROR_FRAME, nextSeq++, 0, (const uint8_t *)message, strlen(message));
}

/* Reads one frame into payload; 0 on success, FSW_SIL_LINK_FAILED or FSW_SIL_PROTOCOL_ERROR with the reason. */
static int receiveFrame(FswTransport *t, uint32_t *type, uint32_t *seq, uint64_t *timeNs, Buffer *payload,
                        char *error, size_t errorSize)
{
    uint8_t header[HEADER_SIZE];
    uint32_t version, length;
    if (t->receive(t, header, HEADER_SIZE) != 0) {
        snprintf(error, errorSize, "the simulation closed the link");
        return FSW_SIL_LINK_FAILED;
    }
    if (memcmp(header, "SMSL", 4) != 0) {
        snprintf(error, errorSize, "received a frame without the SMSL magic");
        return FSW_SIL_PROTOCOL_ERROR;
    }
    version = get16(header + 4);
    if (version != FSW_SIL_CONTRACT_VERSION) {
        snprintf(error, errorSize, "the simulation speaks SIL contract version %u, this flight software %u",
                 (unsigned)version, (unsigned)FSW_SIL_CONTRACT_VERSION);
        return FSW_SIL_PROTOCOL_ERROR;
    }
    *type = get16(header + 6);
    *seq = get32(header + 8);
    length = get32(header + 12);
    *timeNs = get64(header + 16);
    if (length > MAX_PAYLOAD) {
        snprintf(error, errorSize, "frame payload of %lu bytes is over the limit", (unsigned long)length);
        return FSW_SIL_PROTOCOL_ERROR;
    }
    if (reserve(payload, length > 0 ? length : 1) != 0) {
        snprintf(error, errorSize, "out of memory");
        return FSW_SIL_PROTOCOL_ERROR;
    }
    payload->size = length;
    if (length > 0 && t->receive(t, payload->data, length) != 0) {
        snprintf(error, errorSize, "the simulation closed the link inside a frame");
        return FSW_SIL_LINK_FAILED;
    }
    if (crc32Of(payload->data, length) != get32(header + 24)) {
        snprintf(error, errorSize, "frame payload fails its CRC-32");
        return FSW_SIL_PROTOCOL_ERROR;
    }
    return 0;
}

static int appendPort(Buffer *b, const FswPort *port)
{
    uint8_t length, size[4];
    size_t nameLength = strlen(port->name), typeLength = strlen(port->messageType);
    if (nameLength > 255 || typeLength > 255 || strlen(port->layoutHash) != 16) {
        return -1;
    }
    length = (uint8_t)nameLength;
    if (append(b, &length, 1) || append(b, port->name, nameLength)) {
        return -1;
    }
    length = (uint8_t)typeLength;
    put32(size, port->size);
    return append(b, &length, 1) || append(b, port->messageType, typeLength) || append(b, size, 4)
           || append(b, port->layoutHash, 16);
}

static int buildHello(Buffer *b, const char *token)
{
    uint8_t field[20];
    size_t nameLength = strlen(fsw_spacecraft_name);
    size_t i;
    if (strlen(token) != TOKEN_LENGTH || strlen(fsw_config_digest) != DIGEST_LENGTH || nameLength > 0xFFFFu) {
        return -1;
    }
    put16(field, (uint32_t)nameLength);
    if (append(b, token, TOKEN_LENGTH) || append(b, field, 2) || append(b, fsw_spacecraft_name, nameLength)
        || append(b, fsw_config_digest, DIGEST_LENGTH)) {
        return -1;
    }
    put64(field, fsw_rate_ns);
    put32(field + 8, (uint32_t)fsw_input_port_count);
    put32(field + 12, (uint32_t)fsw_output_port_count);
    put32(field + 16, (uint32_t)fsw_telemetry_port_count);
    if (append(b, field, 20)) {
        return -1;
    }
    for (i = 0; i < fsw_input_port_count; i++) {
        if (appendPort(b, &fsw_input_ports[i])) return -1;
    }
    for (i = 0; i < fsw_output_port_count; i++) {
        if (appendPort(b, &fsw_output_ports[i])) return -1;
    }
    for (i = 0; i < fsw_telemetry_port_count; i++) {
        if (appendPort(b, &fsw_telemetry_ports[i])) return -1;
    }
    return 0;
}

/* Writes the written inputs of a RESET or STEP payload; -1 when its size is wrong. */
static int applyInputs(const Buffer *payload, uint64_t timeNs)
{
    size_t i, at = 0, expected = 0;
    for (i = 0; i < fsw_input_port_count; i++) {
        expected += 1u + fsw_input_ports[i].size;
    }
    if (payload->size != expected) {
        return -1;
    }
    for (i = 0; i < fsw_input_port_count; i++) {
        const FswPort *port = &fsw_input_ports[i];
        if (payload->data[at] > 1u) {
            return -1;
        }
        if (payload->data[at] == 1u) {
            port->write(payload->data + at + 1, timeNs);
        }
        at += 1u + port->size;
    }
    return 0;
}

static int appendOutputs(Buffer *b, const FswPort *ports, size_t count, Buffer *scratch)
{
    size_t i;
    for (i = 0; i < count; i++) {
        uint8_t written;
        if (reserve(scratch, ports[i].size > 0 ? ports[i].size : 1) != 0) {
            return -1;
        }
        memset(scratch->data, 0, ports[i].size);
        written = (uint8_t)(ports[i].read(scratch->data) ? 1 : 0);
        if (!written) {
            memset(scratch->data, 0, ports[i].size);
        }
        if (append(b, &written, 1) || append(b, scratch->data, ports[i].size)) {
            return -1;
        }
    }
    return 0;
}

static int fail(FswTransport *t, int status, const char *reason, char *error, size_t errorSize)
{
    snprintf(error, errorSize, "%s", reason);
    if (status == FSW_SIL_PROTOCOL_ERROR) {
        sendError(t, reason);
    }
    return status;
}

int fsw_sil_serve(FswTransport *t, const char *token, char *error, size_t errorSize)
{
    Buffer in = {NULL, 0, 0}, out = {NULL, 0, 0}, scratch = {NULL, 0, 0};
    uint32_t type, seq;
    uint64_t timeNs;
    int status, reset = 0;

    activeTransport = t;
    nextSeq = 0;
    if (token == NULL || strlen(token) != TOKEN_LENGTH) {
        status = fail(t, FSW_SIL_PROTOCOL_ERROR, "no 32-character session token in " FSW_SIL_TOKEN_ENV, error,
                      errorSize);
        goto done;
    }
    if (buildHello(&out, token) != 0 || sendFrame(t, HELLO, nextSeq++, 0, out.data, out.size) != 0) {
        status = fail(t, FSW_SIL_LINK_FAILED, "cannot send HELLO", error, errorSize);
        goto done;
    }
    status = receiveFrame(t, &type, &seq, &timeNs, &in, error, errorSize);
    if (status != 0) {
        if (status == FSW_SIL_PROTOCOL_ERROR) {
            sendError(t, error);
        }
        goto done;
    }
    if (type == ERROR_FRAME) {
        snprintf(error, errorSize, "the simulation refused this flight software: %.*s", (int)in.size,
                 (const char *)in.data);
        status = FSW_SIL_REFUSED;
        goto done;
    }
    if (type != HELLO_ACK) {
        status = fail(t, FSW_SIL_PROTOCOL_ERROR, "expected HELLO_ACK after HELLO", error, errorSize);
        goto done;
    }
    fsw_init();

    for (;;) {
        status = receiveFrame(t, &type, &seq, &timeNs, &in, error, errorSize);
        if (status != 0) {
            if (status == FSW_SIL_PROTOCOL_ERROR) {
                sendError(t, error);
            }
            goto done;
        }
        if (type == RESET) {
            if (reset) {
                fsw_init(); /* a second RESET starts the flight software over */
            }
            if (applyInputs(&in, timeNs) != 0) {
                status = fail(t, FSW_SIL_PROTOCOL_ERROR, "RESET payload does not match the input ports", error,
                              errorSize);
                goto done;
            }
            fsw_reset(timeNs);
            reset = 1;
            if (sendFrame(t, RESET_ACK, seq, timeNs, NULL, 0) != 0) {
                status = fail(t, FSW_SIL_LINK_FAILED, "cannot send RESET_ACK", error, errorSize);
                goto done;
            }
        } else if (type == STEP) {
            uint64_t started, elapsed;
            uint8_t execution[8];
            if (!reset) {
                status = fail(t, FSW_SIL_PROTOCOL_ERROR, "STEP before RESET", error, errorSize);
                goto done;
            }
            if (applyInputs(&in, timeNs) != 0) {
                status = fail(t, FSW_SIL_PROTOCOL_ERROR, "STEP payload does not match the input ports", error,
                              errorSize);
                goto done;
            }
            started = monotonicNs();
            fsw_step(timeNs);
            elapsed = monotonicNs() - started;
            out.size = 0;
            put64(execution, elapsed);
            if (append(&out, execution, 8) || appendOutputs(&out, fsw_output_ports, fsw_output_port_count, &scratch)
                || appendOutputs(&out, fsw_telemetry_ports, fsw_telemetry_port_count, &scratch)) {
                status = fail(t, FSW_SIL_LINK_FAILED, "out of memory", error, errorSize);
                goto done;
            }
            if (sendFrame(t, OUTPUT, seq, timeNs, out.data, out.size) != 0) {
                status = fail(t, FSW_SIL_LINK_FAILED, "cannot send OUTPUT", error, errorSize);
                goto done;
            }
        } else if (type == BYE) {
            sendFrame(t, BYE, seq, timeNs, NULL, 0);
            status = FSW_SIL_DONE;
            goto done;
        } else if (type == ERROR_FRAME) {
            snprintf(error, errorSize, "the simulation stopped the run: %.*s", (int)in.size, (const char *)in.data);
            status = FSW_SIL_REFUSED;
            goto done;
        } else {
            char reason[96];
            snprintf(reason, sizeof reason, "unexpected frame type %u", (unsigned)type);
            status = fail(t, FSW_SIL_PROTOCOL_ERROR, reason, error, errorSize);
            goto done;
        }
    }
done:
    activeTransport = NULL;
    free(in.data);
    free(out.data);
    free(scratch.data);
    return status;
}

void fsw_sil_report_error(const char *message)
{
    if (activeTransport != NULL) {
        sendError(activeTransport, message);
    }
}
