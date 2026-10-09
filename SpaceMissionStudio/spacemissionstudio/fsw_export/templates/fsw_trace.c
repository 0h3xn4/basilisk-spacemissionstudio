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

/* Trace files (fsw_trace.h). */

#include <stdio.h>
#include <string.h>

#include "fsw_trace.h"

static const char traceMagic[8] = {'S', 'M', 'S', 'F', 'T', 'R', 'C', '1'};

static int readU32(FILE *file, uint32_t *value)
{
    return fread(value, sizeof *value, 1, file) == 1 ? 0 : -1;
}

int fsw_trace_open(FswTrace *trace, const char *path, uint32_t kind, const FswPort *const *ports,
                   uint32_t portCount, char *error, size_t errorSize)
{
    char magic[8];
    uint32_t i;
    memset(trace, 0, sizeof *trace);
    trace->file = fopen(path, "rb");
    if (trace->file == NULL) {
        snprintf(error, errorSize, "cannot open %s", path);
        return -1;
    }
    if (fread(magic, 1, sizeof magic, trace->file) != sizeof magic || memcmp(magic, traceMagic, sizeof magic) != 0) {
        snprintf(error, errorSize, "%s is not a trace file (no SMSFTRC1 header)", path);
        return -1;
    }
    if (readU32(trace->file, &trace->kind) || readU32(trace->file, &trace->portCount)
        || readU32(trace->file, &trace->recordCount)) {
        snprintf(error, errorSize, "%s: truncated header", path);
        return -1;
    }
    if (trace->kind != kind) {
        snprintf(error, errorSize, "%s holds kind %u, expected %u", path, (unsigned)trace->kind, (unsigned)kind);
        return -1;
    }
    if (trace->portCount != portCount) {
        snprintf(error, errorSize, "%s has %u ports, this build has %u", path, (unsigned)trace->portCount,
                 (unsigned)portCount);
        return -1;
    }
    for (i = 0; i < portCount; i++) {
        uint32_t size;
        char hash[17] = {0};
        if (readU32(trace->file, &size) || fread(hash, 1, 16, trace->file) != 16) {
            snprintf(error, errorSize, "%s: truncated port table", path);
            return -1;
        }
        if (size != ports[i]->size || memcmp(hash, ports[i]->layoutHash, 16) != 0) {
            snprintf(error, errorSize, "%s: port %u (%s) is %u bytes, layout %s; this build has %u bytes, layout %s",
                     path, (unsigned)i, ports[i]->name, (unsigned)size, hash, (unsigned)ports[i]->size,
                     ports[i]->layoutHash);
            return -1;
        }
    }
    return 0;
}

int fsw_trace_read(FswTrace *trace, uint64_t *timeNs, uint8_t *written, void *const *payloads,
                   const FswPort *const *ports)
{
    uint32_t i;
    if (fread(timeNs, sizeof *timeNs, 1, trace->file) != 1) {
        return feof(trace->file) ? 0 : -1;
    }
    if (fread(written, 1, trace->portCount, trace->file) != trace->portCount) {
        return -1;
    }
    for (i = 0; i < trace->portCount; i++) {
        if (fread(payloads[i], 1, ports[i]->size, trace->file) != ports[i]->size) {
            return -1;
        }
    }
    return 1;
}

int fsw_trace_create(FswTrace *trace, const char *path, uint32_t kind, const FswPort *const *ports,
                     uint32_t portCount, uint32_t recordCount)
{
    uint32_t i;
    memset(trace, 0, sizeof *trace);
    trace->file = fopen(path, "wb");
    if (trace->file == NULL) {
        return -1;
    }
    trace->kind = kind;
    trace->portCount = portCount;
    trace->recordCount = recordCount;
    fwrite(traceMagic, 1, sizeof traceMagic, trace->file);
    fwrite(&kind, sizeof kind, 1, trace->file);
    fwrite(&portCount, sizeof portCount, 1, trace->file);
    fwrite(&recordCount, sizeof recordCount, 1, trace->file);
    for (i = 0; i < portCount; i++) {
        fwrite(&ports[i]->size, sizeof ports[i]->size, 1, trace->file);
        fwrite(ports[i]->layoutHash, 1, 16, trace->file);
    }
    return ferror(trace->file) ? -1 : 0;
}

int fsw_trace_write(FswTrace *trace, uint64_t timeNs, const uint8_t *written, const void *const *payloads,
                    const FswPort *const *ports)
{
    uint32_t i;
    fwrite(&timeNs, sizeof timeNs, 1, trace->file);
    fwrite(written, 1, trace->portCount, trace->file);
    for (i = 0; i < trace->portCount; i++) {
        fwrite(payloads[i], 1, ports[i]->size, trace->file);
    }
    return ferror(trace->file) ? -1 : 0;
}

void fsw_trace_close(FswTrace *trace)
{
    if (trace->file != NULL) {
        fclose(trace->file);
        trace->file = NULL;
    }
}
