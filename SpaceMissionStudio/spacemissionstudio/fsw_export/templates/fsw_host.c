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
 * fsw_host: runs the exported flight software on the host.
 *
 *   fsw_host info
 *       the ports, their payload types, sizes and layout hashes
 *   fsw_host replay <inputs.trace> <outputs.trace> [--expect <expected.trace>] [--rtol R] [--atol A]
 *       feeds a recorded input trace through the flight software, writes every
 *       output and telemetry port to <outputs.trace>, and with --expect compares
 *       them with a recorded run (exit status 1 if any value is out of tolerance)
 *   fsw_host sil <address>
 *       runs the flight software software-in-the-loop: connects to the simulation at
 *       <address> (unix:<path> or tcp:127.0.0.1:<port>) and serves the SIL contract
 *       (SIL_CONTRACT.md) with the session token from the SMS_SIL_TOKEN environment variable
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fsw_ports.h"
#include "fsw_scheduler.h"
#include "fsw_sil.h"
#include "fsw_trace.h"
#include "fsw_transport.h"
#ifdef FSW_HAVE_BSK_LOG
#include "fsw_log.h"
#endif

#define MAX_PORTS 64

static void printPorts(const char *title, const FswPort *ports, size_t count)
{
    size_t i;
    printf("%s (%u):\n", title, (unsigned)count);
    for (i = 0; i < count; i++) {
        printf("  %-40s %-18s %6u bytes  layout %s\n", ports[i].name, ports[i].messageType, (unsigned)ports[i].size,
               ports[i].layoutHash);
    }
}

static int info(void)
{
    printf("flight software of %s, rate %.9g s, configuration %s\n", fsw_spacecraft_name,
           (double)fsw_rate_ns * 1.0e-9, fsw_config_digest);
    printPorts("inputs", fsw_input_ports, fsw_input_port_count);
    printPorts("outputs", fsw_output_ports, fsw_output_port_count);
    printPorts("telemetry", fsw_telemetry_ports, fsw_telemetry_port_count);
    return 0;
}

static void *allocate(size_t size)
{
    void *block = calloc(1, size ? size : 1);
    if (block == NULL) {
        fprintf(stderr, "fsw_host: out of memory\n");
        exit(2);
    }
    return block;
}

static int replay(const char *inputPath, const char *outputPath, const char *expectPath, double rtol, double atol)
{
    const FswPort *in[MAX_PORTS], *out[MAX_PORTS];
    void *inData[MAX_PORTS], *outData[MAX_PORTS], *expData[MAX_PORTS];
    uint8_t inWritten[MAX_PORTS], outWritten[MAX_PORTS], expWritten[MAX_PORTS];
    double worst[MAX_PORTS] = {0.0};
    uint32_t nIn = (uint32_t)fsw_input_port_count;
    uint32_t nOut = (uint32_t)(fsw_output_port_count + fsw_telemetry_port_count);
    uint32_t i, step = 0, failures = 0;
    char error[512];
    FswTrace inputs, outputs, expected;
    uint64_t timeNs, expTimeNs;
    int status;

    if (nIn > MAX_PORTS || nOut > MAX_PORTS) {
        fprintf(stderr, "fsw_host: more than %d ports\n", MAX_PORTS);
        return 2;
    }
    for (i = 0; i < nIn; i++) {
        in[i] = &fsw_input_ports[i];
        inData[i] = allocate(in[i]->size);
    }
    for (i = 0; i < nOut; i++) {
        out[i] = i < fsw_output_port_count ? &fsw_output_ports[i] : &fsw_telemetry_ports[i - fsw_output_port_count];
        outData[i] = allocate(out[i]->size);
        expData[i] = allocate(out[i]->size);
    }
    if (fsw_trace_open(&inputs, inputPath, FSW_TRACE_INPUTS, in, nIn, error, sizeof error) != 0) {
        fprintf(stderr, "fsw_host: %s\n", error);
        return 2;
    }
    if (expectPath != NULL
        && fsw_trace_open(&expected, expectPath, FSW_TRACE_OUTPUTS, out, nOut, error, sizeof error) != 0) {
        fprintf(stderr, "fsw_host: %s\n", error);
        return 2;
    }
    if (fsw_trace_create(&outputs, outputPath, FSW_TRACE_OUTPUTS, out, nOut, inputs.recordCount - 1) != 0) {
        fprintf(stderr, "fsw_host: cannot write %s\n", outputPath);
        return 2;
    }

    fsw_init();
    if (fsw_trace_read(&inputs, &timeNs, inWritten, inData, in) != 1) {
        fprintf(stderr, "fsw_host: %s has no reset record\n", inputPath);
        return 2;
    }
    for (i = 0; i < nIn; i++) {
        if (inWritten[i]) {
            in[i]->write(inData[i], timeNs);
        }
    }
    fsw_reset(timeNs);
    while ((status = fsw_trace_read(&inputs, &timeNs, inWritten, inData, in)) == 1) {
        for (i = 0; i < nIn; i++) {
            if (inWritten[i]) {
                in[i]->write(inData[i], timeNs);
            }
        }
        fsw_step(timeNs);
        for (i = 0; i < nOut; i++) {
            outWritten[i] = (uint8_t)(out[i]->read(outData[i]) ? 1 : 0);
        }
        fsw_trace_write(&outputs, timeNs, outWritten, (const void *const *)outData, out);
        if (expectPath != NULL) {
            if (fsw_trace_read(&expected, &expTimeNs, expWritten, expData, out) != 1 || expTimeNs != timeNs) {
                fprintf(stderr, "fsw_host: %s ends or differs in time at step %u\n", expectPath, (unsigned)step);
                return 2;
            }
            for (i = 0; i < nOut; i++) {
                double maxError = 0.0;
                if (!outWritten[i] && expWritten[i]) {
                    if (failures < 20) {
                        fprintf(stderr, "step %u (t = %.9g s): %s was not written\n", (unsigned)step,
                                (double)timeNs * 1.0e-9, out[i]->name);
                    }
                    failures++;
                } else if (!fsw_payloads_match(out[i], outData[i], expData[i], rtol, atol, &maxError)) {
                    if (failures < 20) {
                        fprintf(stderr, "step %u (t = %.9g s): %s differs, max |error| %.3g\n", (unsigned)step,
                                (double)timeNs * 1.0e-9, out[i]->name, maxError);
                    }
                    failures++;
                }
                if (maxError > worst[i]) {
                    worst[i] = maxError;
                }
            }
        }
        step++;
    }
    fsw_trace_close(&inputs);
    fsw_trace_close(&outputs);
    if (status < 0) {
        fprintf(stderr, "fsw_host: %s is truncated\n", inputPath);
        return 2;
    }
    printf("replayed %u steps\n", (unsigned)step);
    if (expectPath != NULL) {
        fsw_trace_close(&expected);
        for (i = 0; i < nOut; i++) {
            printf("  %-48s max |error| %.3g\n", out[i]->name, worst[i]);
        }
        printf("%s\n", failures ? "MISMATCH" : "all outputs match");
        return failures ? 1 : 0;
    }
    return 0;
}

static int sil(const char *address)
{
    FswTransport transport;
    char error[512];
    int status;
    if (fsw_transport_connect(&transport, address, error, sizeof error) != 0) {
        fprintf(stderr, "fsw_host: %s\n", error);
        return FSW_SIL_LINK_FAILED;
    }
#ifdef FSW_HAVE_BSK_LOG
    fsw_set_error_handler(fsw_sil_report_error);
#endif
    status = fsw_sil_serve(&transport, getenv(FSW_SIL_TOKEN_ENV), error, sizeof error);
    transport.close(&transport);
    if (status != FSW_SIL_DONE) {
        fprintf(stderr, "fsw_host: %s\n", error);
    }
    return status;
}

int main(int argc, char **argv)
{
    const char *expect = NULL;
    double rtol = 1.0e-9, atol = 1.0e-12;
    int i;
    if (argc >= 2 && strcmp(argv[1], "info") == 0) {
        return info();
    }
    if (argc == 3 && strcmp(argv[1], "sil") == 0) {
        return sil(argv[2]);
    }
    if (argc >= 4 && strcmp(argv[1], "replay") == 0) {
        for (i = 4; i + 1 < argc; i += 2) {
            if (strcmp(argv[i], "--expect") == 0) {
                expect = argv[i + 1];
            } else if (strcmp(argv[i], "--rtol") == 0) {
                rtol = atof(argv[i + 1]);
            } else if (strcmp(argv[i], "--atol") == 0) {
                atol = atof(argv[i + 1]);
            } else {
                fprintf(stderr, "fsw_host: unknown option %s\n", argv[i]);
                return 2;
            }
        }
        return replay(argv[2], argv[3], expect, rtol, atol);
    }
    fprintf(stderr, "usage: fsw_host info\n"
                    "       fsw_host replay <inputs.trace> <outputs.trace> [--expect <expected.trace>]"
                    " [--rtol R] [--atol A]\n"
                    "       fsw_host sil <unix:path | tcp:127.0.0.1:port>\n");
    return 2;
}
