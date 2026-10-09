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

/* Leaf-by-leaf payload comparison (fsw_ports.h). */

#include <math.h>
#include <stdint.h>
#include <string.h>

#include "fsw_ports.h"

static double leafValue(const unsigned char *at, FswLeafKind kind, int *isFloat)
{
    *isFloat = 0;
    switch (kind) {
    case FSW_LEAF_F64: { double v; memcpy(&v, at, sizeof v); *isFloat = 1; return v; }
    case FSW_LEAF_F32: { float v; memcpy(&v, at, sizeof v); *isFloat = 1; return (double)v; }
    case FSW_LEAF_I8: { int8_t v; memcpy(&v, at, sizeof v); return (double)v; }
    case FSW_LEAF_U8: { uint8_t v; memcpy(&v, at, sizeof v); return (double)v; }
    case FSW_LEAF_I16: { int16_t v; memcpy(&v, at, sizeof v); return (double)v; }
    case FSW_LEAF_U16: { uint16_t v; memcpy(&v, at, sizeof v); return (double)v; }
    case FSW_LEAF_I32: { int32_t v; memcpy(&v, at, sizeof v); return (double)v; }
    case FSW_LEAF_U32: { uint32_t v; memcpy(&v, at, sizeof v); return (double)v; }
    case FSW_LEAF_I64: { int64_t v; memcpy(&v, at, sizeof v); return (double)v; }
    default: { uint64_t v; memcpy(&v, at, sizeof v); return (double)v; }
    }
}

static size_t leafSize(FswLeafKind kind)
{
    switch (kind) {
    case FSW_LEAF_F64: case FSW_LEAF_I64: case FSW_LEAF_U64: return 8;
    case FSW_LEAF_F32: case FSW_LEAF_I32: case FSW_LEAF_U32: return 4;
    case FSW_LEAF_I16: case FSW_LEAF_U16: return 2;
    default: return 1;
    }
}

int fsw_payloads_match(const FswPort *port, const void *actual, const void *expected, double rtol, double atol,
                       double *maxAbsError)
{
    const unsigned char *a = (const unsigned char *)actual;
    const unsigned char *e = (const unsigned char *)expected;
    double worst = 0.0;
    int match = 1;
    uint32_t i, j;
    for (i = 0; i < port->leafCount; i++) {
        const FswLeaf *leaf = &port->leaves[i];
        size_t size = leafSize(leaf->kind);
        for (j = 0; j < leaf->count; j++) {
            int isFloat;
            size_t offset = leaf->offset + j * size;
            double va = leafValue(a + offset, leaf->kind, &isFloat);
            double ve = leafValue(e + offset, leaf->kind, &isFloat);
            if (isFloat) {
                double diff;
                if (isnan(va) || isnan(ve)) {
                    if (!(isnan(va) && isnan(ve))) {
                        match = 0;
                        worst = INFINITY;
                    }
                    continue;
                }
                diff = fabs(va - ve);
                if (diff > worst) {
                    worst = diff;
                }
                if (diff > atol + rtol * fabs(ve)) {
                    match = 0;
                }
            } else if (memcmp(a + offset, e + offset, size) != 0) {
                match = 0;
                if (fabs(va - ve) > worst) {
                    worst = fabs(va - ve);
                }
            }
        }
    }
    if (maxAbsError != NULL) {
        *maxAbsError = worst;
    }
    return match;
}
